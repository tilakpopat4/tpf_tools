import os
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from google import genai
from pydantic import BaseModel, Field

app = FastAPI()

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
    <title>AI Film Score Prompt Generator</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; background-color: #f9f9fb; color: #333; }
        h1 { text-align: center; color: #111; margin-bottom: 5px; }
        p.subtitle { text-align: center; color: #666; margin-bottom: 30px; }
        #drop-zone { border: 2px dashed #4f46e5; border-radius: 12px; padding: 40px; text-align: center; background: #fff; cursor: pointer; transition: background 0.2s; }
        #drop-zone.hover { background: #e0e7ff; }
        #results-container { margin-top: 30px; display: none; }
        .loading { display: none; text-align: center; font-weight: bold; color: #4f46e5; margin-top: 20px; }
        .scene-card { background: #fff; border-radius: 12px; border: 1px solid #e5e7eb; padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
        .scene-header { font-size: 1.25em; font-weight: bold; color: #111827; margin-bottom: 10px; border-bottom: 2px solid #f3f4f6; padding-bottom: 8px; display: flex; justify-content: space-between; }
        .scene-meta { display: flex; gap: 20px; margin-bottom: 15px; font-size: 0.95em; }
        .scene-meta strong { color: #374151; }
        ul { padding-left: 20px; margin: 5px 0 15px 0; }
        .suno-box { background: #f3f4f6; padding: 12px; border-radius: 8px; border: 1px solid #e5e7eb; position: relative; margin-top: 10px; display: flex; justify-content: space-between; align-items: center; }
        .suno-text { font-family: monospace; font-size: 1em; color: #111827; word-break: break-all; margin-right: 15px; }
        .copy-btn { background: #4f46e5; color: white; border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 0.85em; font-weight: 500; white-space: nowrap; }
        .copy-btn:hover { background: #4338ca; }
    </style>
</head>
<body>

    <h1>🎬 Film Score Prompt Generator</h1>
    <p class="subtitle">Drag & drop your script PDF to break down scenes & generate Suno AI prompts</p>

    <div id="drop-zone">Drag & Drop your script PDF here, or click to select</div>
    <input type="file" id="file-input" accept=".pdf" style="display: none;">

    <div id="loading" class="loading">Analyzing script scenes with Gemini... Please wait...</div>

    <div id="results-container">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h2 style="margin: 0;">🎵 Generated Musical Parameters per Scene</h2>
            <button id="download-pdf-btn" class="copy-btn" style="background: #10b981; font-size: 1em; padding: 10px 20px;">Download Analysis PDF</button>
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

                if (!response.ok) throw new Error('Failed to process PDF');

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
                            <div><strong>BPM:</strong> ${scene.bpm}</div>
                            <div><strong>Mood:</strong> ${scene.mood}</div>
                        </div>
                        <div><strong>Suggested Instrumentation:</strong></div>
                        <ul>${instListHtml}</ul>
                        <div><strong>🔥 Suno AI Prompt:</strong></div>
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
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
        
    finally:
        # Cleanup temporary local file
        if os.path.exists(temp_path):
            os.remove(temp_path)