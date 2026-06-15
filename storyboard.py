import os
import traceback
import base64
import io
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

app = FastAPI()

# 1. Define the desired Gemini output structure for Storyboarding
class StoryboardFrame(BaseModel):
    frame_number: int = Field(description="The sequential number of the storyboard frame.")
    scene_location: str = Field(description="The scene header/location (e.g. INT. COFFEE SHOP - DAY).")
    action_description: str = Field(description="A concise description of the visual action happening in this frame.")
    camera_shot_type: str = Field(description="The camera angle and shot type (e.g. Extreme Close Up, Low Angle Medium Shot, Wide Establishing Shot).")
    camera_movement: str = Field(description="The camera movement (e.g. Static, Pan Left, Slow Push-in, Tilt Up, Tracking Shot).")
    characters_present: list[str] = Field(description="List of characters appearing in this specific shot.")
    visual_notes: str = Field(description="Key styling, lighting, mood, color palette, or composition notes for the frame.")
    image_prompt: str = Field(description="A highly descriptive visual prompt to generate this exact frame's illustration using an image generation model (e.g., 'A dramatic low angle medium shot of a man looking nervously at his phone in a dark room, storyboard pencil sketch, high contrast, cinematic').")
    image_b64: str = Field(default="", description="Base64 encoded string of the generated storyboard image.")

class StoryboardResponse(BaseModel):
    frames: list[StoryboardFrame] = Field(description="A list of sequentially structured storyboard frames mapping the script.")

# 2. HTML Frontend UI for Storyboard Maker
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Film Storyboard Maker</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 1000px; margin: 40px auto; padding: 20px; background-color: #f8fafc; color: #1e293b; }
        h1 { text-align: center; color: #0f172a; margin-bottom: 5px; font-weight: 800; font-size: 2.2em; }
        p.subtitle { text-align: center; color: #64748b; margin-bottom: 35px; font-size: 1.1em; }
        #drop-zone { border: 2px dashed #3b82f6; border-radius: 16px; padding: 50px 30px; text-align: center; background: #fff; cursor: pointer; transition: all 0.2s ease; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }
        #drop-zone:hover { border-color: #2563eb; background: #f0f7ff; }
        #drop-zone.hover { background: #e0f2fe; border-color: #0284c7; }
        #results-container { margin-top: 40px; display: none; }
        .loading { display: none; text-align: center; font-weight: bold; color: #2563eb; margin-top: 20px; font-size: 1.1em; }
        .frame-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 30px; margin-top: 20px; }
        @media(max-width: 768px) {
            .frame-grid { grid-template-columns: 1fr; }
        }
        .frame-card { background: #fff; border-radius: 16px; border: 1px solid #e2e8f0; padding: 24px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); display: flex; flex-direction: column; justify-content: space-between; }
        .frame-image-container { width: 100%; height: 250px; background: #f1f5f9; border-radius: 12px; margin-bottom: 18px; display: flex; align-items: center; justify-content: center; overflow: hidden; border: 1px solid #e2e8f0; }
        .frame-image { width: 100%; height: 100%; object-fit: cover; }
        .frame-badge { background: #eff6ff; color: #1d4ed8; padding: 4px 12px; border-radius: 9999px; font-weight: 700; font-size: 0.85em; width: fit-content; margin-bottom: 12px; }
        .frame-title { font-size: 1.15em; font-weight: 700; color: #0f172a; margin-bottom: 15px; border-bottom: 1px solid #f1f5f9; padding-bottom: 8px; }
        .meta-group { display: flex; flex-direction: column; gap: 8px; margin-bottom: 15px; font-size: 0.95em; }
        .meta-item { display: flex; gap: 8px; }
        .meta-label { font-weight: 700; color: #64748b; width: 110px; flex-shrink: 0; }
        .meta-val { color: #334155; }
        .action-text { font-size: 0.95em; line-height: 1.5; color: #334155; background: #f8fafc; padding: 12px; border-radius: 8px; border: 1px solid #f1f5f9; margin-bottom: 15px; }
        .action-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; }
        .btn-primary { background: #0f172a; color: white; border: none; padding: 12px 24px; border-radius: 10px; cursor: pointer; font-size: 1em; font-weight: 600; display: flex; align-items: center; gap: 8px; transition: background 0.2s; }
        .btn-primary:hover { background: #1e293b; }
    </style>
</head>
<body>

    <h1>🎬 AI Film Storyboard Maker</h1>
    <p class="subtitle">Upload script PDF to generate visual storyboards & PDF report</p>

    <div id="drop-zone">Drag & Drop your script PDF here, or click to select</div>
    <input type="file" id="file-input" accept=".pdf" style="display: none;">

    <div id="loading" class="loading">Analyzing script and drawing storyboard frames... This takes a minute...</div>

    <div id="results-container">
        <div class="action-header">
            <h2 style="margin: 0; font-weight: 800; font-size: 1.5em; color: #0f172a;">Visual Storyboard</h2>
            <button id="download-pdf-btn" class="btn-primary">Download Storyboard PDF</button>
        </div>
        <div id="frames-grid" class="frame-grid"></div>
    </div>

    <!-- Load jsPDF library -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>

    <script>
        const dropZone = document.getElementById('drop-zone');
        const fileInput = document.getElementById('file-input');
        const loading = document.getElementById('loading');
        const resultsContainer = document.getElementById('results-container');
        const framesGrid = document.getElementById('frames-grid');
        const downloadPdfBtn = document.getElementById('download-pdf-btn');
        let currentStoryboardData = null;

        dropZone.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', (e) => handleFile(e.target.files[0]));

        ['dragenter', 'dragover'].forEach(name => {
            dropZone.addEventListener(name, (e) => { e.preventDefault(); dropZone.classList.add('hover'); });
        });
        ['dragleave', 'drop'].forEach(name => {
            dropZone.addEventListener(name, (e) => { e.preventDefault(); dropZone.classList.remove('hover'); });
        });

        dropZone.addEventListener('drop', (e) => {
            const file = e.dataTransfer.files[0];
            if (file && file.type === "application/pdf") {
                handleFile(file);
            } else {
                alert("Please drop a valid PDF file.");
            }
        });

        // Generate PDF Storyboard with images
        downloadPdfBtn.addEventListener('click', () => {
            if (!currentStoryboardData || !currentStoryboardData.frames) return;

            const { jsPDF } = window.jspdf;
            const doc = new jsPDF({
                orientation: 'portrait',
                unit: 'mm',
                format: 'a4'
            });

            const pageHeight = doc.internal.pageSize.getHeight();
            const margin = 20;
            let y = margin;

            function printText(text, fontSize, isBold = false, color = [30, 41, 59], lineSpacing = 5) {
                doc.setFont("helvetica", isBold ? "bold" : "normal");
                doc.setFontSize(fontSize);
                doc.setTextColor(color[0], color[1], color[2]);
                
                const splitText = doc.splitTextToSize(text, 170);
                splitText.forEach(line => {
                    if (y + lineSpacing > pageHeight - margin - 10) {
                        doc.addPage();
                        y = margin;
                    }
                    doc.text(line, margin, y);
                    y += lineSpacing;
                });
            }

            // Title
            printText("FILM PRODUCTION STORYBOARD", 16, true, [15, 23, 42], 10);
            printText("GENERATED VISUAL SEQUENCE SHOTS", 9, true, [100, 116, 139], 6);
            y += 4;
            doc.setDrawColor(226, 232, 240);
            doc.setLineWidth(0.4);
            doc.line(margin, y, 190, y);
            y += 10;

            // Render frames
            currentStoryboardData.frames.forEach(frame => {
                // Approximate height needed per frame is ~105mm (70mm image + text descriptions)
                if (y + 105 > pageHeight - margin) {
                    doc.addPage();
                    y = margin;
                }

                // Header
                printText(`SHOT ${frame.frame_number}: ${frame.scene_location.toUpperCase()}`, 11, true, [15, 23, 42], 7);

                // Draw Storyboard Image if exists
                if (frame.image_b64) {
                    try {
                        const imgData = `data:image/jpeg;base64,${frame.image_b64}`;
                        doc.addImage(imgData, 'JPEG', margin, y, 100, 60); // 100x60mm frame image
                        
                        // Metadata column to the right of the image (x: 125 to 190)
                        doc.setFont("helvetica", "bold");
                        doc.setFontSize(8);
                        doc.setTextColor(100, 116, 139);
                        doc.text("SHOT TYPE:", 127, y + 4);
                        doc.setFont("helvetica", "normal");
                        doc.setTextColor(30, 41, 59);
                        doc.text(frame.camera_shot_type, 127, y + 8);

                        doc.setFont("helvetica", "bold");
                        doc.setTextColor(100, 116, 139);
                        doc.text("MOVEMENT:", 127, y + 15);
                        doc.setFont("helvetica", "normal");
                        doc.setTextColor(30, 41, 59);
                        doc.text(frame.camera_movement, 127, y + 19);

                        doc.setFont("helvetica", "bold");
                        doc.setTextColor(100, 116, 139);
                        doc.text("CHARACTERS:", 127, y + 26);
                        doc.setFont("helvetica", "normal");
                        doc.setTextColor(30, 41, 59);
                        doc.text(frame.characters_present.join(', ') || 'None', 127, y + 30);

                        // Visual Style notes
                        doc.setFont("helvetica", "bold");
                        doc.setTextColor(100, 116, 139);
                        doc.text("VISUAL STYLE:", 127, y + 37);
                        doc.setFont("helvetica", "normal");
                        doc.setTextColor(30, 41, 59);
                        const splitNotes = doc.splitTextToSize(frame.visual_notes, 63);
                        doc.text(splitNotes, 127, y + 41);

                        y += 63;
                    } catch (e) {
                        console.error("Failed to add image to PDF", e);
                        y += 5;
                    }
                }

                // Action description below image
                doc.setFont("helvetica", "bold");
                doc.setFontSize(8.5);
                doc.setTextColor(100, 116, 139);
                doc.text("ACTION:", margin, y);
                doc.setFont("helvetica", "normal");
                doc.setTextColor(30, 41, 59);
                const splitAction = doc.splitTextToSize(frame.action_description, 150);
                doc.text(splitAction, margin + 18, y);
                y += Math.max(6, splitAction.length * 4.5);

                y += 6; // Spacing after block
                doc.setDrawColor(241, 245, 249);
                doc.line(margin, y, 190, y);
                y += 8;
            });

            // Pagination footer
            const pageCount = doc.internal.getNumberOfPages();
            for (let i = 1; i <= pageCount; i++) {
                doc.setPage(i);
                doc.setFont("helvetica", "normal");
                doc.setFontSize(8);
                doc.setTextColor(148, 163, 184);
                doc.text(`Page ${i} of ${pageCount}`, 190, pageHeight - 10, { align: "right" });
            }

            doc.save('film_storyboard.pdf');
        });

        // Helper to convert Image URL to Base64 in-browser using Canvas (more robust CORS handling)
        function toDataURL(url) {
            return new Promise((resolve, reject) => {
                const img = new Image();
                img.crossOrigin = 'Anonymous';
                img.onload = () => {
                    const canvas = document.createElement('canvas');
                    canvas.width = img.naturalWidth;
                    canvas.height = img.naturalHeight;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0);
                    const dataURL = canvas.toDataURL('image/jpeg');
                    resolve(dataURL.split(',')[1]);
                };
                img.onerror = (err) => reject(err);
                img.src = url;
            });
        }

        async function handleFile(file) {
            if (!file) return;
            
            loading.style.display = 'block';
            resultsContainer.style.display = 'none';
            framesGrid.innerHTML = '';
            currentStoryboardData = null;

            const formData = new FormData();
            formData.append('file', file);

            try {
                const response = await fetch('/generate-storyboard', {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) throw new Error('Failed to analyze script');

                const data = await response.json();
                
                if (!data.frames || data.frames.length === 0) {
                    alert('No storyboard frames could be constructed.');
                    return;
                }

                currentStoryboardData = data;

                // Create and mount all cards first with image src referencing Pollinations.ai URL directly
                data.frames.forEach((frame, index) => {
                    const card = document.createElement('div');
                    card.className = 'frame-card';
                    card.id = `frame-card-${index}`;

                    const refinedPrompt = `${frame.image_prompt}, black and white storyboard pencil sketch, film composition, high contrast, hand-drawn charcoal aesthetic, clean ink sketch lines`;
                    const encodedPrompt = encodeURIComponent(refinedPrompt);
                    const imageUrl = `https://image.pollinations.ai/prompt/${encodedPrompt}?width=640&height=360&nologo=true&seed=${index + 42}`;

                    const chars = frame.characters_present.join(', ') || 'None';

                    card.innerHTML = `
                        <div>
                            <div class="frame-image-container" id="img-container-${index}">
                                <img class="frame-image" src="${imageUrl}" crossorigin="anonymous">
                            </div>
                            <div class="frame-badge">Shot ${frame.frame_number}</div>
                            <div class="frame-title">${frame.scene_location}</div>
                            
                            <div class="meta-group">
                                <div class="meta-item">
                                    <span class="meta-label">Shot Type:</span>
                                    <span class="meta-val">${frame.camera_shot_type}</span>
                                </div>
                                <div class="meta-item">
                                    <span class="meta-label">Movement:</span>
                                    <span class="meta-val">${frame.camera_movement}</span>
                                </div>
                                <div class="meta-item">
                                    <span class="meta-label">Characters:</span>
                                    <span class="meta-val">${chars}</span>
                                </div>
                                <div class="meta-item">
                                    <span class="meta-label">Visual Style:</span>
                                    <span class="meta-val">${frame.visual_notes}</span>
                                </div>
                            </div>
                            
                            <div class="action-text">
                                <strong>Visual Action:</strong><br>
                                ${frame.action_description}
                            </div>
                        </div>
                    `;
                    framesGrid.appendChild(card);
                });

                resultsContainer.style.display = 'block';

                // Pre-cache Base64 in background solely for PDF download support
                data.frames.forEach(async (frame, index) => {
                    const refinedPrompt = `${frame.image_prompt}, black and white storyboard pencil sketch, film composition, high contrast, hand-drawn charcoal aesthetic, clean ink sketch lines`;
                    const encodedPrompt = encodeURIComponent(refinedPrompt);
                    const imageUrl = `https://image.pollinations.ai/prompt/${encodedPrompt}?width=640&height=360&nologo=true&seed=${index + 42}`;

                    try {
                        const base64Data = await toDataURL(imageUrl);
                        frame.image_b64 = base64Data;
                    } catch (err) {
                        console.warn(`Could not cache base64 for frame ${index} (PDF export might omit image):`, err);
                    }
                });

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
    """Serves the main frontend page."""
    return HTML_CONTENT

@app.post("/generate-storyboard")
async def generate_storyboard(file: UploadFile = File(...)):
    """Receives script PDF, maps it to visual frames, calls Gemini Imagen, and returns JSON."""
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    temp_path = f"temp_sb_{file.filename}"
    with open(temp_path, "wb") as f:
        f.write(await file.read())

    try:
        client = genai.Client()
        uploaded_file = client.files.upload(file=temp_path)

        prompt = (
            "You are a professional film storyboard artist and visual director. "
            "Analyze the attached script file. "
            "Break down the script sequentially into key visual frames/shots (max 6 shots total to keep execution fast). For each frame, "
            "provide the shot number, scene location/header, action description, shot type/angle, "
            "camera movement, list of characters visible, aesthetic/visual style notes, and a detailed "
            "image generation prompt (to create a black and white storyboard charcoal sketch or illustration representing this shot)."
        )

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[uploaded_file, prompt],
            config={
                "response_mime_type": "application/json",
                "response_schema": StoryboardResponse,
            },
        )

        # Cleanup file from Gemini servers
        client.files.delete(name=uploaded_file.name)
        
        parsed_response = response.parsed

        # We offload the image generation to the client-side frontend script
        # to fetch from the user's browser, preventing server-side proxy rate-limits or 402 blocks.
        return parsed_response

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
        
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
