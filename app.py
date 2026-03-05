"""
Flask web UI for the UPSC Infographic Generator.
Browse chapters, and generate infographics from the pre-loaded book.
"""

import os
from flask import Flask, render_template, request, jsonify, send_file
from src.gemini_client import extract_chapters, generate_infographic, _find_book_pdf

app = Flask(__name__)

# Directories
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


@app.route("/")
def index():
    """Serve the main UI page."""
    return render_template("app.html")


@app.route("/chapters", methods=["GET"])
def get_chapters():
    """Extract chapter titles from the pre-loaded PDF, return JSON."""
    pdf_path = _find_book_pdf()
    if not pdf_path:
        return jsonify({"error": "No book found in the books/ directory. Please ask the admin to upload one."}), 404

    # Extract chapters
    try:
        chapters = extract_chapters(pdf_path)
    except Exception as e:
        return jsonify({"error": f"Failed to extract chapters: {str(e)}"}), 500

    if not chapters:
        return jsonify({"error": "No chapters found in this PDF."}), 400

    book_name = os.path.basename(pdf_path)

    return jsonify({
        "book_name": book_name,
        "chapters": chapters,
        "count": len(chapters),
    })


@app.route("/generate", methods=["POST"])
def generate():
    """Generate an infographic for a selected chapter."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request"}), 400

    chapter = data.get("chapter")

    if not chapter:
        return jsonify({"error": "Missing chapter name"}), 400

    pdf_path = _find_book_pdf()
    if not pdf_path:
        return jsonify({"error": "No book found"}), 404

    try:
        # Generate infographic image directly
        filename = generate_infographic(chapter, pdf_path=pdf_path)

        # Return the filename so the client can request it
        return jsonify({
            "success": True,
            "filename": filename,
            "title": chapter,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Generation failed: {str(e)}"}), 500


@app.route("/output/<filename>")
def serve_output(filename):
    """Serve a generated infographic image."""
    file_path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404
    return send_file(file_path, mimetype="image/jpeg")


if __name__ == "__main__":
    # Use PORT from environment for cloud deployment, default to 5000
    port = int(os.environ.get("PORT", 5000))
    # host='0.0.0.0' makes the server accessible on the local network (and for cloud/docker)
    app.run(host='0.0.0.0', port=port, debug=True)
