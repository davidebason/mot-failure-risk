"""The Azure Function: once a day, land in raw what motrisk.fetch_scheduled.watch finds new.

Deployed by publish.sh, which first copies the motrisk package next to this file.
"""

import logging

import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

from motrisk import fetch, fetch_scheduled

# The Azure libraries log every HTTP request they make at INFO; keep only their warnings and errors.
logging.getLogger("azure").setLevel(logging.WARNING)

app = func.FunctionApp()


# Six fields, seconds first (second minute hour day month weekday): every day at 00:00:00 UTC.
@app.timer_trigger(schedule="0 0 0 */1 * *", arg_name="timer", run_on_startup=False)
def scheduler(timer: func.TimerRequest) -> None:
    """Land each file watch calls "new" or "changed". timer is passed by the runtime, unused."""
    # On Azure, DefaultAzureCredential is the Function's own identity, which holds the storage role.
    credential = DefaultAzureCredential()
    service = BlobServiceClient(
        account_url="https://stmotrisk.blob.core.windows.net", credential=credential
    )
    container = service.get_container_client("raw")
    rel, decisions = fetch_scheduled.watch(container)

    n = 0
    for name, word in decisions:
        if word != "same":
            result = fetch.upload_with_retries(container, name, rel[name])
            logging.info("uploaded %s: %d bytes", name, result["size"])
            n += 1

    logging.info("uploaded %d files", n)
