from google_drive_service import upload_file_to_drive

link = upload_file_to_drive(
    "test.png",
    "image/png"
)

print(link)