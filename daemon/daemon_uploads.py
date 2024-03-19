"""Holds functionality for asset uploads.
Extends upload.py on addon side."""

import asyncio
import json
import os
import typing
from logging import getLogger
from pathlib import Path

import daemon_globals
import daemon_tasks
import daemon_utils
from aiohttp import ClientSession, web


logger = getLogger(f"daemon.{__name__}")
BLENDERKIT_EXPORT_DATA_FILE = "data.json"


async def do_asset_upload(request: web.Request, task: daemon_tasks.Task):
    """Upload asset to server."""
    # METADATA UPLOAD or DOWNLOAD
    if "METADATA" in task.data["upload_set"]:
        task.change_progress(1, "posting metadata")
        error, metadata_response = await upload_metadata(
            request.app["SESSION_API_REQUESTS"], task
        )
        if error != "":
            task.error(f"Metadata upload failed: {error}")
            return
    else:
        task.change_progress(1, "getting metadata")
        error, metadata_response = await get_metadata(
            request.app["SESSION_API_REQUESTS"], task
        )
        if error != "":
            task.error(f"Metadata download failed: {error}")
            return

    task.data["asset_data"] = metadata_response
    metadata_upload_task = daemon_tasks.Task(
        task.data, task.app_id, "asset_metadata_upload"
    )
    metadata_upload_task.finished("Metadata successfully uploaded")
    daemon_globals.tasks.append(metadata_upload_task)

    # FILE PACKING
    task.change_progress(5, "packing files")
    error, files = await pack_blend_file(task, metadata_response)
    if error != "":
        return task.error(error)

    # ASSET FILES UPLOAD
    task.change_progress(20, "uploading files")
    error = await upload_asset_data(request.app["SESSION_UPLOADS"], task, files)
    if error != "":
        task.error(f"Asset upload failed: {error}")
        return

    # SET UPLOAD STATUS
    task.change_progress(98, "setting asset status")
    error = await ensure_verificationStatus(
        request.app["SESSION_API_REQUESTS"], task, metadata_response
    )
    if error != "":
        task.error(f"Asset status setting failed: {error}")
        return

    # FINALIZE UPLOAD
    if "THUMBNAIL" in task.data["upload_set"] or "MAINFILE" in task.data["upload_set"]:
        task.change_progress(99, "finalizing upload")
        error = await finalize_upload_request(request.app["SESSION_API_REQUESTS"], task)
        if error != "":
            task.error(f"Upload finalization failed: {error}")
            return

    logger.info("Upload task finished")
    task.finished("Asset successfully uploaded.")


async def upload_metadata(session: ClientSession, task: daemon_tasks.Task):
    """Upload metadata to server, so it can be saved inside the current file."""
    url = f"{daemon_globals.SERVER}/api/v1/assets/"
    upload_data = task.data["upload_data"]
    export_data = task.data["export_data"]
    upload_set = task.data["upload_set"]

    upload_data["parameters"] = daemon_utils.dict_to_params(
        upload_data["parameters"]
    )  # weird array conversion only for upload, not for tooltips.
    headers = daemon_utils.get_headers(upload_data["token"])
    json_metadata = upload_data

    if export_data["assetBaseId"] == "":
        try:
            resp_text, resp_status = None, -1
            async with session.post(url, json=json_metadata, headers=headers) as resp:
                resp_status = resp.status
                resp_text = await resp.text()
                resp.raise_for_status()
                logger.info(f"POST metadata successful ({resp.status}) for {url}")
                resp_json = await resp.json()
                return "", resp_json
        except Exception as e:
            msg, detail = daemon_utils.extract_error_message(
                e, resp_text, resp_status, "Upload metadata"
            )
            logger.error(detail)
            return msg, None

    url = f'{url}{export_data["id"]}/'
    if (
        "MAINFILE" in upload_set
    ):  # quite hidden place to change the status, should be in do_asset_upload explicitly
        json_metadata["verificationStatus"] = "uploading"
    try:
        resp_text, resp_status = None, -1
        async with session.patch(url, json=json_metadata, headers=headers) as response:
            resp_status = response.status
            resp_text = await response.text()
            response.raise_for_status()
            logger.info(f"PATCH metadata succesfful ({response.status}) for {url}")
            resp_json = await response.json()
            return "", resp_json
    except Exception as e:
        msg, detail = daemon_utils.extract_error_message(
            e, resp_text, resp_status, "Metadata upload"
        )
        logger.error(detail)
        return msg, None


async def get_metadata(session: ClientSession, task: daemon_tasks.Task):
    """Get metadata from server."""
    asset_id = task.data["export_data"]["id"]
    headers = daemon_utils.get_headers(task.data["upload_data"]["token"])
    url = f"{daemon_globals.SERVER}/api/v1/assets/{asset_id}/"
    try:
        resp_text, resp_status = None, -1
        async with session.get(url, headers=headers) as resp:
            resp_status = resp.status
            resp_text = await resp.text()
            resp.raise_for_status()
            logger.info(f"GET metadata successful ({resp.status}) for {url}")
            resp_json = await resp.json()
            return "", resp_json
    except Exception as e:
        msg, detail = daemon_utils.extract_error_message(
            e, resp_text, resp_status, "Get metadata"
        )
        logger.error(detail)
        return msg, None


async def pack_blend_file(task: daemon_tasks.Task, metadata_response: dict):
    """Pack the asset data into a separate clean blend file.
    This runs a script inside Blender in separate process.
    """
    addon_path = Path(__file__).resolve().parents[1]  # ../daemon/daemon_uploads.py
    blender_user_scripts_dir = (
        Path(__file__).resolve().parents[3]
    )  # scripts/addons/blenderkit/daemon/daemon_uploads.py
    script_path = str(addon_path.joinpath("upload_bg.py"))
    cleanfile_path = str(addon_path.joinpath("blendfiles", "cleaned.blend"))
    upload_data = task.data["upload_data"]
    export_data = task.data["export_data"]
    upload_set = task.data["upload_set"]

    if export_data["assetBaseId"] == "":
        export_data["assetBaseId"] = metadata_response["assetBaseId"]
        export_data["id"] = metadata_response["id"]
    upload_data["assetBaseId"] = export_data["assetBaseId"]
    upload_data["id"] = export_data["id"]

    if "MAINFILE" in upload_set:
        if upload_data["assetType"] == "hdr":
            fpath = export_data["hdr_filepath"]
        else:
            fpath = os.path.join(
                export_data["temp_dir"], upload_data["assetBaseId"] + ".blend"
            )
            data = {
                "export_data": export_data,
                "upload_data": upload_data,
                "upload_set": upload_set,
            }
            datafile = os.path.join(
                export_data["temp_dir"], BLENDERKIT_EXPORT_DATA_FILE
            )
            logger.info("opening file @ pack_blend_file()")
            with open(datafile, "w", encoding="utf-8") as s:
                json.dump(data, s, ensure_ascii=False, indent=4)

            task.change_progress(10, "preparing scene - running blender instance")
            logger.info("Running asset packing")
            env = {"BLENDER_USER_SCRIPTS": str(blender_user_scripts_dir)}
            env.update(os.environ)
            process = await asyncio.create_subprocess_exec(
                export_data["binary_path"],
                "--background",
                "--factory-startup",  # disables user preferences, addons, etc.
                "--addons",
                "blenderkit",
                "-noaudio",
                cleanfile_path,
                "--python",
                script_path,
                "--",
                datafile,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
            )
            stdout, _ = await process.communicate()
            if process.returncode != 0:
                msg = f"Asset packing failed ({process.returncode}) - check daemon log for details."
                out = stdout.decode()
                logger.error(f"Packing failed ({process.returncode}):\n{out}")
                return msg, None

    files = []
    if "THUMBNAIL" in upload_set:
        files.append(
            {
                "type": "thumbnail",
                "index": 0,
                "file_path": export_data["thumbnail_path"],
            }
        )
    if "MAINFILE" in upload_set:
        files.append({"type": "blend", "index": 0, "file_path": fpath})
        if not os.path.exists(fpath):
            return "packed file does not exist, please try manual packing first", None

    return "", files


async def upload_asset_data(
    session: ClientSession,
    task: daemon_tasks.Task,
    files: list,
) -> str:
    """Upload .blend file and/or thumbnail to the server."""
    for file in files:
        upload_info_json, ok = await get_S3_upload_JSON(task, session, file)
        if not ok:
            return "failed to get S3 upload info"

        ok, error = await upload_file_to_S3(session, task, file, upload_info_json)
        if not ok:
            return error

    return ""


async def get_S3_upload_JSON(
    task: daemon_tasks.Task, session: ClientSession, file: dict
) -> tuple[dict, bool]:
    url = f"{daemon_globals.SERVER}/api/v1/uploads/"
    headers = daemon_utils.get_headers(task.data["upload_data"]["token"])
    upload_info = {
        "assetId": task.data["upload_data"]["id"],
        "fileType": file["type"],
        "fileIndex": file["index"],
        "originalFilename": os.path.basename(file["file_path"]),
    }
    try:
        resp_text, resp_json = None, None
        async with session.post(url, json=upload_info, headers=headers) as resp:
            resp_text = await resp.text()
            resp.raise_for_status()
            resp_json = await resp.json()
            return resp_json, True
    except Exception as e:
        logger.error(f"{type(e)}: {e}, {resp_text}, {resp_json}")
        return None, False


async def upload_file_to_S3(
    session: ClientSession, task: daemon_tasks.Task, file: dict, upload_info_json: dict
) -> typing.Tuple[bool, str]:
    """Uploads file to S3, returns True if successful, error message returned as second value.
    First try to upload file, then validate the upload on server, server returns error if upload failed (wrong file).
    """
    headers = daemon_utils.get_headers(task.data["upload_data"]["token"])

    # FILE UPLOAD
    with open(file["file_path"], "rb") as binary_file:
        logger.info(f"Uploading {file['type']} file {file['file_path']} to S3")
        try:
            resp_text, resp_status = None, -1
            async with session.put(
                upload_info_json["s3UploadUrl"],
                data=binary_file,
            ) as resp:
                resp_status = resp.status
                resp_text = await resp.text()
                resp.raise_for_status()
        except Exception as e:
            msg, detail = daemon_utils.extract_error_message(
                e, resp_text, resp_status, "S3 upload"
            )
            logger.warning(detail)
            return False, msg
    logger.info("File uploaded to S3")

    # UPLOAD VALIDATION
    upload_done_url = f'{daemon_globals.SERVER}/api/v1/uploads_s3/{upload_info_json["id"]}/upload-file/'
    try:
        resp_text, resp_status = None, -1
        async with await session.post(upload_done_url, headers=headers) as resp:
            resp_status = resp.status
            resp_text = await resp.text()
            resp.raise_for_status()
    except Exception as e:
        msg, detail = daemon_utils.extract_error_message(
            e, resp_text, resp_status, "S3 confirmation"
        )
        logger.warning(detail)
        return False, msg

    task.change_progress(task.progress + 15)
    logger.info("File upload confirmed with BlenderKit server")
    return True, ""


async def ensure_verificationStatus(
    session: ClientSession, task: daemon_tasks.Task, metadata_response: dict
) -> str:
    """Ensure asset verificationStatus is set to uploaded if needed. Logic is:
    - if MAINFILE is uploaded, set status to uploaded
    - if THUMBNAIL or METADATA is uploaded and the asset is on_hold, deleted or rejected, set status to uploaded
    - otherwise do not set the status to uploaded.
    """
    uploaded_status_required = False
    if "MAINFILE" in task.data["upload_set"]:
        uploaded_status_required = True
    if metadata_response.get("verificationStatus") in (
        "on_hold",
        "deleted",
        "rejected",
    ):
        uploaded_status_required = True

    if uploaded_status_required is False:
        return ""

    # Set status to uploaded on server
    confirm_data = {"verificationStatus": "uploaded"}
    headers = daemon_utils.get_headers(task.data["upload_data"]["token"])
    url = f"{daemon_globals.SERVER}/api/v1/assets/{task.data['upload_data']['id']}/"
    try:
        resp_text, resp_status = None, -1
        async with session.patch(url, json=confirm_data, headers=headers) as resp:
            resp_status = resp.status
            resp_text = await resp.text()
            resp.raise_for_status()
            logger.info(f"Asset verificationStatus was set to uploaded")
            return ""
    except Exception as e:
        msg, detail = daemon_utils.extract_error_message(
            e, resp_text, resp_status, "Patch assset failed"
        )
        logger.error(detail)
        return msg


async def finalize_upload_request(
    session: ClientSession, task: daemon_tasks.Task
) -> str:
    """Finalize upload by making POST request to server, called after the upload is successfully finished.
    This triggers the server to start processing the asset.
    """
    asset_base_id = task.data["upload_data"]["assetBaseId"]
    headers = daemon_utils.get_headers(task.data["upload_data"]["token"])
    url = f"{daemon_globals.SERVER}/api/v1/assets/{asset_base_id}/finalize/"
    try:
        resp_text, resp_status = None, -1
        async with session.post(url, headers=headers) as resp:
            resp_status = resp.status
            resp_text = await resp.text()
            resp.raise_for_status()
            logger.info(f"Upload finalization successful")
            return ""
    except Exception as e:
        msg, detail = daemon_utils.extract_error_message(
            e, resp_text, resp_status, "Finalize upload"
        )
        logger.error(detail)
        return msg
