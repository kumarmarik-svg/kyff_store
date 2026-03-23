from flask import jsonify


def error(message, code=400):
    """Shortcut for returning JSON error responses."""
    return jsonify({"success": False, "message": message}), code


def success(message, data=None, code=200):
    """Shortcut for returning JSON success responses."""
    response = {"success": True, "message": message}
    if data:
        response["data"] = data
    return jsonify(response), code
