import httpx
import backend.config as config

job_id = "video_bGl0ZWxsbTpjdXN0b21fbGxtX3Byb3ZpZGVyOnZlcnRleF9haTttb2RlbF9pZDp2ZW8tMy4xLWdlbmVyYXRlLTAwMTt2aWRlb19pZDpwcm9qZWN0cy9raGFyLXplcm8tMTIwOC9sb2NhdGlvbnMvZ2xvYmFsL3B1Ymxpc2hlcnMvZ29vZ2xlL21vZGVscy92ZW8tMy4xLWdlbmVyYXRlLTAwMS9vcGVyYXRpb25zL2RmZmJjMDc1LTcxNWMtNGMxOS05YzA3LTJmMzI0M2MwZmZkZA=="

headers = {"Authorization": f"Bearer {config.LOCAL_API_KEY}"}
base = "https://litellm.maskhar.com"

endpoints = [
    f"{base}/v1/videos/{job_id}",
    f"{base}/v1/videos/jobs/{job_id}",
    f"{base}/v1/video/jobs/{job_id}",
    f"{base}/v1/operations/{job_id}",
]

for url in endpoints:
    try:
        r = httpx.get(url, headers=headers, timeout=10)
        print(f"[{r.status_code}] {url}")
        print(r.text[:400])
        print("---")
    except Exception as e:
        print(f"[ERROR] {url}: {e}")
        print("---")