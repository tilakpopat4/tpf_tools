import os
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from google import genai
from pydantic import BaseModel, Field

app = FastAPI()

# Mount the static directory (using absolute path for Vercel serverless compatibility)
static_path = os.path.join(os.path.dirname(__file__), "public")
if os.path.exists(static_path):
    app.mount("/public", StaticFiles(directory=static_path), name="public")

# 1. Define the desired Gemini output structure
class ScenePrompt(BaseModel):
    scene_number: int = Field(description="The sequential number of the scene.")
    scene_title: str = Field(description="The scene header or location/time (e.g. INT. LIVING ROOM - DAY).")
    bpm: int = Field(description="The suggested beats per minute (BPM) for this scene.")
    mood: str = Field(description="The primary emotional mood, vibe, or genre of this scene.")
    instrumentation: list[str] = Field(description="A list of specific instruments suggested for this scene.")
    suno_prompt: str = Field(description="A perfect Suno AI style prompt (under 120 chars, comma-separated tags describing style, instruments, and mood: e.g., 'slow cinematic piano, emotional cello, ambient pads, 75 bpm, pensive').")

class ScriptAnalysisResponse(BaseModel):
    scenes: list[ScenePrompt] = Field(description="A list of music prompts for each scene identified in the script.")

# 2. HTML Frontend UI (Served directly from the root URL)
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TPF Tools - Film Score Prompt Generator</title>
    <link rel="icon" type="image/x-icon" href="/public/favicon.ico?v=2">
    <link rel="icon" type="image/png" sizes="32x32" href="/public/favicon-32.png?v=2">
    <link rel="icon" type="image/png" sizes="192x192" href="/public/favicon-192.png?v=2">
    <!-- Google Font -->
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #f8fafc;
            --card-bg: #ffffff;
            --border-color: #e2e8f0;
            --primary: #4f46e5;
            --primary-hover: #3730a3;
            --accent: #059669;
            --text-main: #0f172a;
            --text-muted: #475569;
        }
        body { 
            font-family: 'Outfit', -apple-system, sans-serif; 
            max-width: 900px; 
            margin: 0 auto; 
            padding: 40px 20px; 
            background-color: var(--bg-color); 
            color: var(--text-main); 
            background-image: radial-gradient(circle at top right, rgba(99, 102, 241, 0.05), transparent 400px),
                              radial-gradient(circle at bottom left, rgba(16, 185, 129, 0.03), transparent 400px);
            background-attachment: fixed;
        }
        
        /* Branding Header */
        .branding-header {
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
            margin-bottom: 40px;
        }
        .branding-logo {
            height: 140px;
            object-fit: contain;
            margin-bottom: 15px;
            filter: drop-shadow(0px 2px 4px rgba(0,0,0,0.05));
        }
        .branding-title {
            font-size: 2.4em;
            font-weight: 800;
            color: var(--text-main);
            margin: 0;
            letter-spacing: -0.03em;
        }
        .subtitle { 
            color: var(--text-muted); 
            font-size: 1.1em;
            margin-top: 6px;
            margin-bottom: 0;
            font-weight: 400;
        }

        /* Drag & Drop Area */
        #drop-zone { 
            border: 2px dashed rgba(99, 102, 241, 0.3); 
            border-radius: 16px; 
            padding: 50px 30px; 
            text-align: center; 
            background: var(--card-bg); 
            cursor: pointer; 
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); 
            backdrop-filter: blur(8px);
            border-color: var(--primary);
            box-shadow: 0 4px 20px -2px rgba(15, 23, 42, 0.05);
        }
        #drop-zone:hover { 
            border-color: var(--accent);
            box-shadow: 0 10px 30px -10px rgba(16, 185, 129, 0.15);
            transform: translateY(-2px);
        }
        #drop-zone.hover { 
            background: rgba(99, 102, 241, 0.05); 
            border-color: var(--accent);
        }
        .drop-icon {
            font-size: 2.5em;
            margin-bottom: 10px;
            display: inline-block;
        }
        .drop-text {
            font-weight: 500;
            font-size: 1.05em;
            color: var(--text-main);
        }

        #results-container { margin-top: 45px; display: none; }
        .loading { 
            display: none; 
            text-align: center; 
            font-weight: 600; 
            color: var(--primary); 
            margin-top: 30px; 
            font-size: 1.1em;
            animation: pulse 1.8s infinite;
        }
        @keyframes pulse {
            0% { opacity: 0.6; }
            50% { opacity: 1; }
            100% { opacity: 0.6; }
        }

        /* Scene Breakdown Cards */
        .scene-card { 
            background: var(--card-bg); 
            border-radius: 16px; 
            border: 1px solid var(--border-color); 
            padding: 24px; 
            margin-bottom: 24px; 
            box-shadow: 0 4px 20px -5px rgba(15, 23, 42, 0.05); 
        }
        .scene-header { 
            font-size: 1.3em; 
            font-weight: 700; 
            color: var(--text-main); 
            margin-bottom: 12px; 
            border-bottom: 1px solid var(--border-color); 
            padding-bottom: 10px; 
            display: flex; 
            justify-content: space-between; 
        }
        .scene-meta { 
            display: flex; 
            gap: 25px; 
            margin-bottom: 18px; 
            font-size: 0.95em; 
        }
        .scene-meta strong { color: var(--text-muted); }
        .scene-meta span { color: var(--text-main); font-weight: 500; }
        .instruments-title {
            font-size: 0.9em;
            font-weight: 700;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 6px;
        }
        ul { padding-left: 20px; margin: 0 0 20px 0; color: #334155; line-height: 1.6; }
        
        /* Suno Prompts Panel */
        .suno-title {
            font-size: 0.9em;
            font-weight: 700;
            color: var(--accent);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .suno-box { 
            background: #f8fafc; 
            padding: 14px 18px; 
            border-radius: 10px; 
            border: 1px solid var(--border-color); 
            position: relative; 
            margin-top: 6px; 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            transition: border-color 0.2s;
        }
        .suno-box:hover {
            border-color: rgba(16, 185, 129, 0.4);
        }
        .suno-text { 
            font-family: monospace; 
            font-size: 0.95em; 
            color: #047857; 
            word-break: break-all; 
            margin-right: 15px; 
        }
        
        /* Buttons */
        .copy-btn { 
            background: var(--primary); 
            color: white; 
            border: none; 
            padding: 8px 16px; 
            border-radius: 8px; 
            cursor: pointer; 
            font-size: 0.85em; 
            font-weight: 600; 
            white-space: nowrap; 
            transition: all 0.2s;
        }
        .copy-btn:hover { 
            background: var(--primary-hover); 
            transform: translateY(-1px);
        }
        .copy-btn:active {
            transform: translateY(0);
        }
        
        .header-actions {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
        }
        .header-actions h2 {
            font-size: 1.5em;
            font-weight: 700;
            margin: 0;
        }
        .download-btn {
            background: var(--accent);
        }
        .download-btn:hover {
            background: #059669;
        }
    </style>
</head>
<body>

    <div class="branding-header">
        <img class="branding-logo" src="/public/logo.png?v=3" alt="TPF Logo">
        <h1 class="branding-title">Film Score Prompt Generator</h1>
        <p class="subtitle">Upload script PDF to segment scenes and render professional Suno AI prompts</p>
    </div>

    <div id="drop-zone">
        <span class="drop-icon">🎬</span>
        <div class="drop-text">Drag & Drop script PDF here, or click to browse</div>
    </div>
    <input type="file" id="file-input" accept=".pdf" style="display: none;">

    <div id="loading" class="loading">Generating score breakdowns with Gemini... Please wait...</div>

    <div id="results-container">
        <div class="header-actions">
            <h2>🎵 Segmented Scenes</h2>
            <button id="download-pdf-btn" class="copy-btn download-btn">Download Report PDF</button>
        </div>
        <div id="scenes-list"></div>
    </div>

    <!-- Load jsPDF library -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>

    <script>
        const dropZone = document.getElementById('drop-zone');
        const fileInput = document.getElementById('file-input');
        const loading = document.getElementById('loading');
        const resultsContainer = document.getElementById('results-container');
        const scenesList = document.getElementById('scenes-list');
        const downloadPdfBtn = document.getElementById('download-pdf-btn');
        let currentAnalysisData = null;

        // Handle click to open file explorer
        dropZone.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', (e) => handleFile(e.target.files[0]));

        // Handle Drag & Drop styling
        ['dragenter', 'dragover'].forEach(name => {
            dropZone.addEventListener(name, (e) => { e.preventDefault(); dropZone.classList.add('hover'); });
        });
        ['dragleave', 'drop'].forEach(name => {
            dropZone.addEventListener(name, (e) => { e.preventDefault(); dropZone.classList.remove('hover'); });
        });

        // Handle File Drop
        dropZone.addEventListener('drop', (e) => {
            const file = e.dataTransfer.files[0];
            if (file && file.type === "application/pdf") {
                handleFile(file);
            } else {
                alert("Please drop a valid PDF file.");
            }
        });

        // Copy Suno Prompt
        function copySunoPrompt(btn, textId) {
            const promptText = document.getElementById(textId).innerText;
            navigator.clipboard.writeText(promptText).then(() => {
                const originalText = btn.innerText;
                btn.innerText = 'Copied!';
                btn.style.background = '#10b981';
                setTimeout(() => {
                    btn.innerText = originalText;
                    btn.style.background = '#4f46e5';
                }, 1500);
            }).catch(err => {
                console.error('Failed to copy: ', err);
            });
        }

        // Export data to PDF using jsPDF
        downloadPdfBtn.addEventListener('click', () => {
            if (!currentAnalysisData || !currentAnalysisData.scenes) return;

            const { jsPDF } = window.jspdf;
            const doc = new jsPDF({
                orientation: 'portrait',
                unit: 'mm',
                format: 'a4'
            });

            const pageHeight = doc.internal.pageSize.getHeight();
            const margin = 20;
            let y = margin;

            // Helper to print text and handle page breaks
            function printText(text, fontSize, isBold = false, color = [31, 41, 55], lineSpacing = 6) {
                doc.setFont("helvetica", isBold ? "bold" : "normal");
                doc.setFontSize(fontSize);
                doc.setTextColor(color[0], color[1], color[2]);
                
                const splitText = doc.splitTextToSize(text, 170); // A4 width (210) - 2 * margin = 170
                splitText.forEach(line => {
                    if (y + lineSpacing > pageHeight - margin - 10) {
                        doc.addPage();
                        y = margin;
                    }
                    doc.text(line, margin, y);
                    y += lineSpacing;
                });
            }

            // Document Title Header (Minimal & Premium)
            printText("FILM SCORE MUSIC ANALYSIS REPORT", 16, true, [17, 24, 39], 10);
            printText("GENERATED VIA GEMINI PROMPT ENGINE", 9, true, [107, 114, 128], 6);
            y += 4;
            
            // Clean separator line
            doc.setDrawColor(229, 231, 235);
            doc.setLineWidth(0.4);
            doc.line(margin, y, 190, y);
            y += 10;

            // Print each scene
            currentAnalysisData.scenes.forEach(scene => {
                // Ensure room for scene header + meta. If tight, start new page.
                if (y + 40 > pageHeight - margin) {
                    doc.addPage();
                    y = margin;
                }

                // Scene Title (Bold, Charcoal)
                printText(`SCENE ${scene.scene_number}: ${scene.scene_title.toUpperCase()}`, 11, true, [17, 24, 39], 7);
                
                // Meta fields formatted cleanly
                doc.setFont("helvetica", "bold");
                doc.setFontSize(9);
                doc.setTextColor(107, 114, 128); // Slate gray for keys
                
                // Row 1: BPM & Mood
                doc.text("BPM:", margin, y);
                doc.setFont("helvetica", "normal");
                doc.setTextColor(31, 41, 55);
                doc.text(String(scene.bpm), margin + 12, y);

                doc.setFont("helvetica", "bold");
                doc.setTextColor(107, 114, 128);
                doc.text("MOOD:", margin + 40, y);
                doc.setFont("helvetica", "normal");
                doc.setTextColor(31, 41, 55);
                
                // Wrap mood value to avoid overflow
                const moodText = scene.mood;
                const splitMood = doc.splitTextToSize(moodText, 110);
                doc.text(splitMood, margin + 55, y);
                y += Math.max(6, splitMood.length * 5);

                // Row 2: Instrumentation
                doc.setFont("helvetica", "bold");
                doc.setTextColor(107, 114, 128);
                doc.text("INSTRUMENTS:", margin, y);
                doc.setFont("helvetica", "normal");
                doc.setTextColor(31, 41, 55);
                const instText = scene.instrumentation.join(', ');
                const splitInst = doc.splitTextToSize(instText, 135);
                doc.text(splitInst, margin + 30, y);
                y += Math.max(6, splitInst.length * 5);

                // Row 3: Suno AI Prompt (Highlighted in subtle light gray panel)
                const sunoPromptText = scene.suno_prompt;
                const splitSuno = doc.splitTextToSize(sunoPromptText, 160);
                const blockHeight = (splitSuno.length * 5) + 6;

                // Check page limit before rendering Suno block
                if (y + blockHeight > pageHeight - margin) {
                    doc.addPage();
                    y = margin;
                }

                // Gray Background box
                doc.setFillColor(249, 250, 251);
                doc.rect(margin, y - 2, 170, blockHeight, "F");
                
                // Draw a thin left border in accent deep indigo color
                doc.setFillColor(79, 70, 229);
                doc.rect(margin, y - 2, 1.5, blockHeight, "F");

                // Print Suno Prompt inside box
                doc.setFont("helvetica", "normal");
                doc.setFontSize(9);
                doc.setTextColor(55, 65, 81);
                splitSuno.forEach(line => {
                    doc.text(line, margin + 5, y + 2);
                    y += 5;
                });

                y += 10; // Spacing after block
            });

            // Footer (Page numbers)
            const pageCount = doc.internal.getNumberOfPages();
            for (let i = 1; i <= pageCount; i++) {
                doc.setPage(i);
                doc.setFont("helvetica", "normal");
                doc.setFontSize(8);
                doc.setTextColor(156, 163, 175);
                doc.text(`Page ${i} of ${pageCount}`, 190, pageHeight - 10, { align: "right" });
            }

            doc.save('film_score_music_analysis.pdf');
        });

        // Upload file to local Python Backend
        async function handleFile(file) {
            if (!file) return;
            
            loading.style.display = 'block';
            resultsContainer.style.display = 'none';
            scenesList.innerHTML = '';
            currentAnalysisData = null;

            const formData = new FormData();
            formData.append('file', file);

            try {
                const response = await fetch('/process-pdf', {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) {
                    const errText = await response.text();
                    throw new Error(errText);
                }

                const data = await response.json();
                
                if (!data.scenes || data.scenes.length === 0) {
                    alert('No scenes identified in the script.');
                    return;
                }

                currentAnalysisData = data;

                // Render each scene
                data.scenes.forEach((scene, index) => {
                    const textId = `suno-text-${index}`;
                    const card = document.createElement('div');
                    card.className = 'scene-card';
                    
                    let instListHtml = scene.instrumentation.map(inst => `<li>${inst}</li>`).join('');

                    card.innerHTML = `
                        <div class="scene-header">
                            <span>Scene ${scene.scene_number}: ${scene.scene_title}</span>
                        </div>
                        <div class="scene-meta">
                            <div><strong>BPM:</strong> <span>${scene.bpm}</span></div>
                            <div><strong>Mood:</strong> <span>${scene.mood}</span></div>
                        </div>
                        <div class="instruments-title">Suggested Instrumentation</div>
                        <ul>${instListHtml}</ul>
                        <div class="suno-title">🔥 Suno AI Prompt</div>
                        <div class="suno-box">
                            <span id="${textId}" class="suno-text">${scene.suno_prompt}</span>
                            <button class="copy-btn" onclick="copySunoPrompt(this, '${textId}')">Copy Prompt</button>
                        </div>
                    `;
                    scenesList.appendChild(card);
                });

                resultsContainer.style.display = 'block';
            } catch (error) {
                alert('Error processing file: ' + error.message);
            } finally {
                loading.style.display = 'none';
            }
        }
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def read_root():
    """Serves the HTML frontend webpage."""
    return HTML_CONTENT

@app.post("/process-pdf")
async def process_pdf(file: UploadFile = File(...)):
    """Receives the PDF from the browser, passes it to Gemini, and returns JSON."""
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    # Save incoming file temporarily in /tmp directory (Vercel allows writing only to /tmp)
    temp_path = f"/tmp/temp_{file.filename}"
    with open(temp_path, "wb") as f:
        f.write(await file.read())

    try:
        # Initialize Gemini Client (reads GEMINI_API_KEY from environment)
        client = genai.Client()

        # Upload to Gemini's File API
        uploaded_file = client.files.upload(file=temp_path)

        prompt = (
            "You are an expert film composer and Suno AI music generation prompt engineer. "
            "Analyze the entire attached script file. "
            "Identify EVERY single separate scene in the script sequentially from beginning to end. "
            "Do not stop or truncate at 20 scenes—make sure you process the entire document. For each and every scene, "
            "determine the scene header/location, suggested BPM, emotional mood, and instrumentation. "
            "Then, create a perfect Suno AI style music prompt (comma-separated style tags, under 120 characters, "
            "e.g. 'cinematic, neo-classical piano, mournful cello, slow tempo, 65 bpm') representing that scene."
        )

        # Generate structured content
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[uploaded_file, prompt],
            config={
                "response_mime_type": "application/json",
                "response_schema": ScriptAnalysisResponse,
            },
        )

        # Cleanup file from Gemini servers
        client.files.delete(name=uploaded_file.name)
        
        # Return structured response
        return response.parsed

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(error_details)
        raise HTTPException(status_code=500, detail=f"Server Error: {str(e)}\n\nTraceback:\n{error_details}")
        
    finally:
        # Cleanup temporary local file
        if os.path.exists(temp_path):
            os.remove(temp_path)