from flask import Flask, request, jsonify
from flask_cors import CORS
import easyocr
import filetype
import os
import json
import numpy as np
from pdf2image import convert_from_path
from PIL import Image

app = Flask(__name__)
CORS(app)

reader = easyocr.Reader(['en'])

# Load prescription requirement mapping
with open('prescription_required.json') as f:
    prescription_required_map = json.load(f)

# Helper function to extract text from a file (image or PDF)
def extract_text_from_file(file):
    text_output = ""

    kind = filetype.guess(file.read(261))
    file.seek(0)

    if kind and kind.mime.startswith("image"):
        img = Image.open(file.stream).convert('RGB')
        result = reader.readtext(np.array(img), detail=0)
        text_output = " ".join(str(r) for r in result)

    elif (kind and "pdf" in kind.mime) or file.filename.lower().endswith(".pdf"):
        temp_path = "temp_prescription.pdf"
        with open(temp_path, 'wb') as f:
            f.write(file.read())

        images = convert_from_path(temp_path, dpi=300)
        for img in images:
            img_np = np.array(img.convert('RGB'))
            result = reader.readtext(img_np, detail=0)
            text_output += " " + " ".join(str(r) for r in result)

        os.remove(temp_path)
    else:
        raise ValueError("Unsupported file type")

    return text_output.strip()

@app.route("/verify-prescription", methods=["POST"])
def verify_prescription():
    if 'desired_items' not in request.form:
        return jsonify({"error": "Missing 'desired_items' in request"}), 400

    try:
        desired_items = json.loads(request.form['desired_items'])
        desired_names = [item["name"].lower() for item in desired_items]

        # Check which medicines require a prescription
        meds_requiring_prescription = [
            name for name in desired_names if prescription_required_map.get(name, False)
        ]
        prescription_required = len(meds_requiring_prescription) > 0

        # Validate uploaded files if prescription is required
        files = request.files.getlist('files')
        if prescription_required and not files:
            return jsonify({
                "error": "Prescription is required for one or more medications but not provided.",
                "medicines_requiring_prescription": meds_requiring_prescription
            }), 400

        # Extract and combine OCR text
        combined_text = ""
        for file in files:
            combined_text += " " + extract_text_from_file(file)

        lower_text = combined_text.lower()

        # Matching logic
        matched_items = [name for name in desired_names if name in lower_text]
        unmatched_items = [item for item in desired_items if item["name"].lower() not in matched_items]
        prescribed_items = [{"medication_name": name.title()} for name in matched_items]

        response = {
            "ocr_text": combined_text.strip(),
            "desired_items": desired_items,
            "prescription_required": prescription_required,
            "medicines_requiring_prescription": meds_requiring_prescription,
            "verification_result": {
                "is_valid_order": bool(matched_items),
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

    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON format in 'desired_items'"}), 400
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True, port=6000)

