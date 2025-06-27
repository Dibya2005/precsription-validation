import os
import io
import json
import numpy as np
from flask import Flask, request, jsonify
from PIL import Image
import easyocr
from pydantic import BaseModel, Field, ValidationError
from typing import List, Optional
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  
reader = easyocr.Reader(['en'])


class DesiredItem(BaseModel):
    name: str
    quantity: Optional[str] = None


def ocr_image_with_easyocr(image_bytes: bytes) -> str:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    image_np = np.array(image)
    result = reader.readtext(image_np, detail=0)
    return " ".join(result)


@app.route("/verify-prescription", methods=["POST"])
def verify_prescription():
    if 'prescription_image' not in request.files:
        return jsonify({"error": "No image uploaded."}), 400

    prescription_file = request.files['prescription_image']
    if not prescription_file.filename.lower().endswith((".png", ".jpg", ".jpeg")):
        return jsonify({"error": "Only PNG, JPG, JPEG image files are supported."}), 400

    try:
        image_bytes = prescription_file.read()
        prescription_text = ocr_image_with_easyocr(image_bytes).lower()

        desired_items_json = request.form.get("desired_items_json", "")
        parsed_json_data = json.loads(desired_items_json)
        desired_items_list = [DesiredItem(**item) for item in parsed_json_data]

        matched_items = []
        unmatched_items = []

        for item in desired_items_list:
            if item.name.lower() in prescription_text:
                matched_items.append(item.name)
            else:
                unmatched_items.append(item.name)

        response = {
            "prescriptionRequired": len(unmatched_items) == 0,
            "matched_items": matched_items,
            "unmatched_desired_items": unmatched_items,
            "prescription_text": prescription_text
        }

        return jsonify(response)

    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON format in desired_items_json."}), 400
    except ValidationError as e:
        return jsonify({"error": f"Validation failed: {e}"}), 400
    except Exception as e:
        return jsonify({"error": f"Unexpected server error: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=6000)
