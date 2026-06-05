# file_service.py

import os
import uuid
import aiofiles
import httpx


TEMP_FOLDER = "temp"
IMAGE_FOLDER = "temp/images"
VIDEO_FOLDER = "temp/videos"


async def download_file(url, extension):

    if extension == "png":
        folder = IMAGE_FOLDER

    elif extension == "mp4":
        folder = VIDEO_FOLDER

    else:
        folder = TEMP_FOLDER

    if not os.path.exists(folder):
        os.makedirs(folder)

    filename = f"{uuid.uuid4()}.{extension}"

    file_path = os.path.join(
        folder,
        filename
    )

    async with httpx.AsyncClient(timeout=300) as client:

        response = await client.get(url)

        response.raise_for_status()

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(response.content)

    return file_path