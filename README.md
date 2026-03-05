# UPSC Infographic Generator 🎓

This is a Python/Flask application that converts UPSC textbook chapters (PDF) into beautiful, high-fidelity study infographics using **Google Gemini 2.0** and **Nano Banana 2**.

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.9 or higher
- A Google Gemini API Key

### 2. Physical Setup
1. Clone or copy the project folder to your machine.
2. Ensure your textbook PDF is in the `books/` folder.

### 3. Environment Configuration
Create a file named `.env` in the root directory and add your API key:
```env
GEMINI_API_KEY=your_key_here
```

### 4. Installation
Install the required Python libraries:
```bash
pip install -r requirements.txt
```

### 5. Running the App
Start the Flask server:
```bash
python app.py
```
Open your browser to `http://localhost:5000` to start generating!

## ☁️ Cloud Deployment
This app is ready for deployment on platforms like **Render**, **Railway**, or **PythonAnywhere**.
- **Host**: `0.0.0.0`
- **Port**: Managed via the `PORT` environment variable.
- **Dependencies**: Listed in `requirements.txt`.

## 🛠️ Tech Stack
- **Backend**: Flask (Python)
- **PDF Engine**: PyMuPDF (fitz)
- **AI Logic**: Gemini 2.0 Flash
- **AI Design**: Nano Banana 2 (Gemini 3.1 Flash Image)
