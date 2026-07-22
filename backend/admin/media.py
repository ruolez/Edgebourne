from flask import jsonify, request

import content
import uploads

from . import bp


@bp.post("/upload")
def upload():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "No file provided"}), 400
    try:
        full, thumb = uploads.save_image(file)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"path": full, "thumb": thumb})


@bp.post("/preview")
def preview():
    md = request.form.get("md")
    if md is None:
        md = (request.get_json(silent=True) or {}).get("md", "")
    return content.render_md(md)
