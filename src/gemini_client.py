"""Gemini API client for generating structured infographic content from a chapter topic."""

import os
import re
import glob
import fitz  # PyMuPDF
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()


def _get_client() -> genai.Client:
    """Initialize and return the Gemini client."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY not found. Create a .env file with:\n"
            "GEMINI_API_KEY=your_key_here"
        )
    return genai.Client(api_key=api_key)


def _find_book_pdf(override_path: str | None = None) -> str | None:
    """Find the first PDF file in the books/ directory, or use the override path."""
    if override_path and os.path.exists(override_path):
        return override_path
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    books_dir = os.path.join(project_root, "books")
    if not os.path.exists(books_dir):
        return None
    pdfs = glob.glob(os.path.join(books_dir, "*.pdf"))
    return pdfs[0] if pdfs else None


def extract_chapters(pdf_path: str) -> list[str]:
    """
    Extract chapter titles from a PDF using its table of contents.
    
    Chapters are identified as L2 (level 2) ToC entries whose titles
    start with a number. This filters out Parts, front matter, appendices,
    and sub-sections.
    
    Falls back to regex-based detection if ToC is empty.
    
    Args:
        pdf_path: Path to the PDF file
    
    Returns:
        List of chapter title strings
    """
    doc = fitz.open(pdf_path)
    
    numbered_pattern = re.compile(r'^\d+\s+')
    
    # Try the built-in ToC first
    toc = doc.get_toc()
    if toc:
        chapters = []
        for level, title, page in toc:
            cleaned = title.strip()
            # Chapters are L2 entries with numbered titles
            if level == 2 and numbered_pattern.match(cleaned):
                chapters.append(cleaned)
        
        if chapters:
            doc.close()
            # Deduplicate while preserving order
            seen = set()
            unique = []
            for ch in chapters:
                if ch not in seen:
                    seen.add(ch)
                    unique.append(ch)
            return unique
    
    # Fallback: scan page text for chapter patterns
    chapters = []
    chapter_pattern = re.compile(
        r'(?:^|\n)\s*(?:Chapter|CHAPTER|Part|PART)?\s+(\d+[\s.:—]+.+?)(?:\n|$)',
        re.MULTILINE
    )
    
    for page_num in range(min(len(doc), 50)):  # Scan first 50 pages for ToC
        page = doc[page_num]
        text = page.get_text()
        matches = chapter_pattern.findall(text)
        for match in matches:
            cleaned = match.strip()
            if len(cleaned) > 3 and len(cleaned) < 150:
                chapters.append(cleaned)
    
    doc.close()
    
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for ch in chapters:
        if ch not in seen:
            seen.add(ch)
            unique.append(ch)
    
    return unique


def _extract_chapter_text(pdf_path: str, topic: str) -> str:
    """
    Extract relevant chapter text from the PDF using the Table of Contents.
    
    Falls back to a keyword search if the topic isn't perfectly matched in the ToC.
    """
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    
    toc = doc.get_toc()
    start_page = -1
    end_page = -1
    
    # 1. Try to find precise bounds using ToC
    if toc:
        for i, entry in enumerate(toc):
            level, title, page = entry
            cleaned_title = title.strip().lower()
            if cleaned_title == topic.strip().lower() or (level == 2 and topic.strip().lower() in cleaned_title):
                start_page = page - 1
                # Find the next entry at the same or higher level to mark the end
                for j in range(i + 1, len(toc)):
                    next_level, _, next_page = toc[j]
                    if next_level <= level:
                        end_page = next_page - 1
                        break
                if end_page == -1:
                    end_page = total_pages - 1
                break
                
    if start_page != -1:
        # We found exact bounds from the TOC
        chapter_text = []
        extract_end = min(end_page, start_page + 60) # Cap at 60 pages
        
        for page_num in range(start_page, extract_end):
            page = doc[page_num]
            text = page.get_text()
            if text.strip():
                chapter_text.append(f"--- Page {page_num + 1} ---\n{text}")
                
        doc.close()
        extracted = "\n\n".join(chapter_text)
        print(f"📄 Extracted {extract_end - start_page} pages (pages {start_page + 1}-{extract_end}) via exact ToC match")
        print(f"   Text length: {len(extracted):,} characters")
        return extracted
        
    print(f"⚠️  Could not find perfect ToC match for '{topic}'. Falling back to keyword search.")
    
    # 2. Fallback: Search for pages containing the topic keywords
    topic_lower = topic.lower()
    keywords = [kw.strip() for kw in topic_lower.split() if len(kw.strip()) > 2]
    
    matching_pages = []
    for page_num in range(total_pages):
        page = doc[page_num]
        text = page.get_text().lower()
        # Check if most keywords appear on this page
        matches = sum(1 for kw in keywords if kw in text)
        if matches >= max(1, len(keywords) // 2):
            matching_pages.append(page_num)
    
    if not matching_pages:
        # Try individual keywords
        for page_num in range(total_pages):
            page = doc[page_num]
            text = page.get_text().lower()
            if any(kw in text for kw in keywords):
                matching_pages.append(page_num)
    
    if not matching_pages:
        print(f"⚠️  Could not find '{topic}' in the book at all. Using Gemini's knowledge base.")
        doc.close()
        return ""
    
    first_match = matching_pages[0]
    
    # We assume the chapter starts close to the first mention
    start_page = max(0, first_match - 1)
    # Give it a ~30 page runway for a chapter size
    end_page = min(total_pages - 1, start_page + 30)
    
    # Extract text from the chapter pages
    chapter_text = []
    for page_num in range(start_page, end_page + 1):
        page = doc[page_num]
        text = page.get_text()
        if text.strip():
            chapter_text.append(f"--- Page {page_num + 1} ---\n{text}")
    
    doc.close()
    
    extracted = "\n\n".join(chapter_text)
    print(f"📄 Extracted {end_page - start_page + 1} pages (pages {start_page + 1}-{end_page + 1}) via Keyword Fallback")
    print(f"   Text length: {len(extracted):,} characters")
    
    return extracted


def generate_infographic(chapter_topic: str, pdf_path: str | None = None) -> str:
    """
    Generate a visual infographic for a UPSC chapter topic using Imagen.
    
    1. Extracts the relevant chapter text from the PDF book.
    2. Uses Gemini to distill the text into a detailed image generation prompt.
    3. Uses Imagen to generate the final infographic image.
    
    Args:
        chapter_topic: The chapter topic.
        pdf_path: Optional path to the PDF file.
    
    Returns:
        str: Filename of the generated image in the output directory.
    """
    client = _get_client()
    
    # --- Step 1: Extract Text ---
    resolved_pdf = _find_book_pdf(pdf_path)
    chapter_text = ""
    
    if resolved_pdf:
        print(f"📚 Using book: {os.path.basename(resolved_pdf)}")
        print(f"📝 Searching for: {chapter_topic}")
        chapter_text = _extract_chapter_text(resolved_pdf, chapter_topic)
    
    # --- Step 2: Generate Prompt (Gemini 2.0 Flash) ---
    print(f"🧠 Distilling content for: {chapter_topic}")
    
    prompt_instruction = f"""You are an expert prompt engineer writing a prompt for Google's Nano Banana 2 (Gemini 3.1 Flash Image) model.

Your task is to write an image generation prompt that produces a NotebookLM-style educational infographic that perfectly balances RICH VECTOR ILLUSTRATIONS with SUBSTANTIAL READABLE TEXT.

REFERENCE STYLE (you must replicate this exact feel):
- Cream/off-white background with soft geometric line patterns
- Multiple distinct visual panels or sections — the EXACT NUMBER AND LAYOUT of panels must be determined by you to proportion the space based on the length and volume of the provided text.
- Text includes: article numbers (e.g., "Article 352"), short explanatory sentences, comparison data (e.g., "Approval Deadline: 1 Month (Special Majority)"), durations, and key facts. Ensure comprehensive, proportional amounts of text.
- A supporting details section with a decorative banner containing multiple items, each with a smaller icon and 1-2 sentence explanation. The number of items must scale with the depth of the provided chapter extract.
- Professional typography, clean vector art style, subtle shading
- The NotebookLM watermark in the bottom right corner

CRITICAL RULES (FOLLOW THESE ABSOLUTELY OR THE GENERATION WILL FAIL):
1. ZERO INACCURACIES: Every word, number, and date must be 100% accurate to the provided text.
2. ZERO SPELLING MISTAKES: Nano Banana 2 is exceptional at rendering text, BUT you must explicitly instruct it to spell every single word perfectly without hallucinating letters. Emphasize to the image generator that spelling is the highest priority constraint.
3. NO LOREM IPSUM OR GIBBERISH: Every word must be real and accurate.
4. TEXT MUST BE COMPREHENSIVE & PROPORTIONAL: Balance rich visuals with substantial arrays of text blocks that capture the true richness of the book's chapter.
5. ILLUSTRATIONS MUST BE DETAILED & PROPORTIONAL: Each text panel/section needs its own relevant vector illustration (e.g., shield with swords for defense, parliament building with gavel for governance).
6. LIGHT THEME ONLY: Cream/off-white background. NO dark backgrounds.

YOUR OUTPUT PROMPT MUST FOLLOW THIS EXACT STRUCTURE:

Start with: "A professional, highly detailed, high-resolution educational infographic poster about '{chapter_topic}' in the NotebookLM style. THE HIGHEST PRIORITY IS PERFECT TEXT RENDERING WITH ABSOLUTELY ZERO SPELLING ERRORS AND ZERO GIBBERISH. EVERY WORD MUST BE SPELLED EXACTLY AS REQUESTED. Cream/off-white background with subtle decorative line patterns. The poster perfectly balances rich vector illustrations with substantial readable text. Clean vector art style, professional typography, subtle gradients and shading. NotebookLM watermark in the bottom-right corner."

Then describe:
1. "TOP HEADER: A large, bold title '[EXACT TITLE]' with a decorative vector illustration of [RELEVANT ICON] between the words. Below, a comprehensive intro paragraph summarizing the topic. The header has subtle decorative borders. THE TEXT MUST BE SPELLED FLAWLESSLY."

2. "MAIN BODY: [N] colored panels arranged in a grid or flow on a cream background.
   - [For EVERY major subtopic in the text, generate a panel description like this]: Titled '[SUBTOPIC] ([ARTICLE/SECTION REF])' on a [COLOR] background, featuring a large detailed vector illustration of [SPECIFIC VISUAL METAPHOR]. Below the illustration: '[2-3 DESCRIPTIVE SENTENCES]'. Data labels: '[LABEL 1]: [FACT]', '[LABEL 2]: [FACT]'. IMPORTANT: Ensure absolute perfect spelling. Repeat for all subtopics."

3. "SUPPORTING DETAILS SECTION: A decorative banner or column containing [N] items.
   - [For EVERY minor subtopic/supporting fact, generate an item description]: Detailed vector icon of [ICON] with text explanation: '[1-2 SENTENCES WITH SPECIFIC FACTS/NAMES/ARTICLES]'. THE TEXT MUST HAVE ZERO SPELLING ERRORS. Repeat for all supporting facts."

IMPORTANT: Replace ALL bracketed placeholders with REAL, SPECIFIC, ACCURATE content from the chapter. Use actual article numbers, names, dates, and facts. Ensure the volume of panels, lists, and text accurately reflects the total breadth of the extracted chapter content. The final output must be ONE prompt producing a single dense, text-rich, visually packed, and perfectly spelled poster image."""

    if chapter_text:
        context_prompt = f"""Here is the chapter text extracted from M. Laxmikanth's 'Indian Polity' textbook about "{chapter_topic}":

<CHAPTER_TEXT>
{chapter_text[:20000]}
</CHAPTER_TEXT>

Based on this textbook content, {prompt_instruction}"""
    else:
        context_prompt = prompt_instruction

    # Call Gemini to get the image prompt
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=context_prompt,
        config=types.GenerateContentConfig(
            temperature=0.7,
        ),
    )
    
    image_prompt = response.text.strip()
    print(f"🎨 Generated Image Prompt:\n{image_prompt}")
    
    # --- Step 3: Generate Image (Nano Banana 2 / Gemini 3.1 Flash Image) ---
    print(f"🖼️ Generating image with Nano Banana 2...")
    
    result = client.models.generate_content(
        model='nano-banana-pro-preview',
        contents=image_prompt,
    )
    
    # Ensure output directory exists
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate filename from title
    filename = chapter_topic.lower()
    filename = ''.join(c if c.isalnum() or c == ' ' else '' for c in filename)
    filename = filename.strip().replace(' ', '_')
    filename = filename[:60] + ".jpg"
    
    output_path = os.path.join(output_dir, filename)
    
    for candidate in result.candidates:
        for part in candidate.content.parts:
            if hasattr(part, 'inline_data') and part.inline_data:
                with open(output_path, "wb") as f:
                    f.write(part.inline_data.data)
                break
            
    print(f"✅ Generated infographic: {output_path}")
    return filename

