from flask import Flask, request, jsonify
from flask_cors import CORS
import easyocr
import filetype
import os
import re
import numpy as np
from pdf2image import convert_from_path
from PIL import Image
import json

app = Flask(__name__)
CORS(app)
reader = easyocr.Reader(['en'])

def extract_text_from_file(file):
    text_output = ""
    kind = filetype.guess(file.read(261))
    file.seek(0)

    if kind and kind.mime.startswith("image"):
        img = Image.open(file.stream).convert('RGB')
        result = reader.readtext(np.array(img), detail=0)
        text_output = " ".join(str(r) for r in result)

    elif "pdf" in (kind.mime if kind else "") or file.filename.endswith(".pdf"):
        temp_path = "temp_prescription.pdf"
        with open(temp_path, 'wb') as f:
            f.write(file.read())

        images = convert_from_path(temp_path, dpi=300)
        for img in images:
            img_np = np.array(img.convert('RGB'))
            result = reader.readtext(img_np, detail=0)
            text_output += " ".join(str(r) for r in result)

        os.remove(temp_path)
    else:
        raise ValueError("Unsupported file type")

    return text_output

@app.route("/verify-prescription", methods=["POST"])
def verify_prescription():
    if 'file' not in request.files or 'desired_items' not in request.form:
        return jsonify({"error": "Missing file or desired_items"}), 400

    file = request.files['file']
    try:
        desired_items = json.loads(request.form['desired_items'])
        desired_names = [item["name"].lower() for item in desired_items]

        ocr_text = extract_text_from_file(file)
        lower_text = ocr_text.lower()

        matched_items = [name for name in desired_names if name in lower_text]
        unmatched_items = [item for item in desired_items if item["name"].lower() not in matched_items]
        prescribed_items = [{"medication_name": name.title()} for name in matched_items]

    
        is_valid_order = len(matched_items) > 0

        response = {
            "ocr_text": ocr_text,
            "desired_items": desired_items,
            "verification_result": {
                "is_valid_order": is_valid_order,
                "identified_prescribed_items": prescribed_items,
                "verification_details": (
                    "All medications found in prescription"
                    if len(matched_items) == len(desired_names)
                    else "Partial match found" if matched_items else "No matches found"
                ),
                "matched_items": [name.title() for name in matched_items],
                "unmatched_desired_items": unmatched_items,
                "additional_notes": (
                    "All requested medications are valid"
                    if not unmatched_items
                    else "Some items missing"
                )
            },
            "message": "Verification complete"
        }
        return jsonify(response)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
