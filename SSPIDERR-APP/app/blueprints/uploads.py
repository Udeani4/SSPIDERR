"""Upload songs -> recognise them -> add them to a playlist."""
import logging

import spotipy
from flask import Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import limiter
from ..models import UploadJob
from ..services import uploads
from ..utils import spotify_required
from .library import cached_playlists

log = logging.getLogger(__name__)
bp = Blueprint("uploads", __name__)


@bp.route("/loader-page")
@spotify_required
def loader_page():
    return render_template("loader-page.html", files=uploads.list_pending(current_user.id),
                           extensions=sorted(current_app.config["UPLOAD_EXTENSIONS"]))


@bp.route("/upload-song", methods=["POST"])
@login_required
@limiter.limit("240 per minute")
def file_upload():
    storage = request.files.get("file")
    if not storage:
        return jsonify({"success": False, "message": "No file uploaded."}), 400
    ok, message, filename = uploads.save_upload(current_user.id, storage)
    if not ok:
        return jsonify({"success": False, "message": message}), 400
    return jsonify({"success": True, "filename": filename})


@bp.route("/uploads/<path:filename>/delete", methods=["POST"])
@login_required
def delete_upload(filename):
    uploads.delete_pending(current_user.id, filename)
    if request.is_json or request.accept_mimetypes.best == "application/json":
        return jsonify({"success": True})
    return redirect(url_for("uploads.display_uploads"))


@bp.route("/display-uploads")
@spotify_required
def display_uploads():
    files = uploads.list_pending(current_user.id)
    running = uploads.active_job(current_user.id)
    if running:
        return redirect(url_for("uploads.show_song_processing", playlist_id=running.playlist_id,
                                job=running.public_id))
    if not files:
        flash("Upload some songs first.", "info")
        return redirect(url_for("uploads.loader_page"))
    playlists = [p for p in cached_playlists(g.sp, current_user) if p["editable"]]
    return render_template("display_uploads.html", files=files, playlist_list=playlists)


@bp.route("/song-processing/<playlist_id>")
@spotify_required
def show_song_processing(playlist_id):
    """Progress page. The page itself starts the job with a POST to /jobs."""
    job = None
    public_id = request.args.get("job")
    if public_id:
        job = UploadJob.query.filter_by(public_id=public_id, user_id=current_user.id).first()
    try:
        playlist = g.sp.playlist(playlist_id, fields="id,name,images")
    except spotipy.SpotifyException:
        abort(404)
    return render_template("song_processing.html", playlist_id=playlist_id, playlist=playlist, job=job,
                           job_missing=bool(public_id) and job is None,
                           retention_days=current_app.config.get("UPLOAD_RESULTS_RETENTION_DAYS", 30),
                           pending=len(uploads.list_pending(current_user.id)))


@bp.route("/jobs", methods=["POST"])
@login_required
def create_job():
    data = request.get_json(silent=True) or request.form
    playlist_id = (data.get("playlist_id") or "").strip()
    if not playlist_id:
        return jsonify({"error": "Choose a playlist first."}), 400
    try:
        job, created = uploads.create_job(current_user, playlist_id, (data.get("playlist_name") or "")[:200] or None)
    except uploads.JobError as exc:
        return jsonify({"error": str(exc)}), 400
    if created:
        uploads.start_job(job)
    return jsonify({"job_id": job.public_id, "status_url": url_for("uploads.job_status", public_id=job.public_id)})


@bp.route("/jobs/<public_id>/status")
@login_required
def job_status(public_id):
    job = UploadJob.query.filter_by(public_id=public_id, user_id=current_user.id).first_or_404()
    return jsonify(uploads.job_status(job))
