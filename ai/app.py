from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
import os
import io
import json
import numpy as np
from PIL import Image
import easyocr
from pydantic import BaseModel, Field, ValidationError
from typing import List, Optional
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

app = Flask(__name__)

# Configuration
app.config['UPLOAD_FOLDER'] = './uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'pdf'}
os.environ["GROQ_API_KEY"] = "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"

# Initialize EasyOCR
reader = easyocr.Reader(['en'])

# --- Pydantic Models ---
class PrescriptionItem(BaseModel):
    medication_name: str = Field(description="Name of the prescribed medication")

class DesiredItem(BaseModel):
    name: str = Field(description="Name of the desired medication")
    quantity: Optional[str] = Field(None, description="Desired quantity")

class VerificationResult(BaseModel):
    is_valid_order: bool
    identified_prescribed_items: List[PrescriptionItem]
    verification_details: str
    matched_items: List[str]
    unmatched_desired_items: List[str]
    additional_notes: Optional[str] = None

# Initialize LLM
llm = ChatGroq(model="llama3-8b-8192", temperature=0.0)
llm_with_tool = llm.with_structured_output(VerificationResult)

prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a medical prescription verification AI. Analyze the prescription text and compare it with desired medications."""),
    ("human", "Prescription:\n{prescription_text}\n\nDesired Items:\n{desired_items_json}")
])

chain = prompt | llm_with_tool

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def ocr_image(image_bytes):
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image_np = np.array(image)
        results = reader.readtext(image_np, detail=0)
        return "\n".join(results)
    except Exception as e:
        raise Exception(f"OCR failed: {str(e)}")

@app.route('/verify-prescription', methods=['POST'])
def verify_prescription():
    if 'prescription_image' not in request.files:
        return jsonify({"error": "No image file provided"}), 400
    
    file = request.files['prescription_image']
    desired_items_json = request.form.get('desired_items_json')
    
    if not file or file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if not allowed_file(file.filename):
        return jsonify({"error": "Invalid file type"}), 400
    
    if not desired_items_json:
        return jsonify({"error": "No desired items provided"}), 400

    try:
        # Process image
        image_bytes = file.read()
        prescription_text = ocr_image(image_bytes)
        
        if not prescription_text.strip():
            return jsonify({"error": "No text extracted from image"}), 400

        # Process desired items
        try:
            desired_items = json.loads(desired_items_json)
            if not isinstance(desired_items, list):
                raise ValueError("Expected JSON array")
        except Exception as e:
            return jsonify({"error": f"Invalid JSON: {str(e)}"}), 400

        # Format for LLM
        desired_items_str = "\n".join(
            f"- {item.get('name')}" + 
            (f" (Quantity: {item['quantity']})" if item.get('quantity') else "")
            for item in desired_items
        )

        # LLM Processing
        result = chain.invoke({
            "prescription_text": prescription_text,
            "desired_items_json": desired_items_str
        })
        
        return jsonify(result.model_dump())

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=True)
