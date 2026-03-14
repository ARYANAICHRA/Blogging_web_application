from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from app.models import Notification

api_bp = Blueprint('api', __name__)


@api_bp.route('/notifications/count')
@login_required
def notification_count():
    count = current_user.unread_notification_count()
    return jsonify({'count': count})
