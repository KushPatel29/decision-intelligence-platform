"""Single immutable container implements SageMaker train and batch serving."""

import io
import os
import sys
from pathlib import Path

import joblib
import pandas as pd
from flask import Flask, Response, request
from portfolio_entry import predictions, train

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if mode == "train":
        from threadpoolctl import threadpool_limits

        with threadpool_limits(limits=1):
            train(
                os.getenv("SM_CHANNEL_TRAIN", "/opt/ml/input/data/train"),
                os.getenv("SM_CHANNEL_VALIDATION", "/opt/ml/input/data/validation"),
                os.getenv("SM_MODEL_DIR", "/opt/ml/model"),
                os.getenv("SM_OUTPUT_DATA_DIR", "/opt/ml/output/data"),
            )
    elif mode == "serve":
        bundle = joblib.load(Path("/opt/ml/model/model.joblib"))
        app = Flask(__name__)
        app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024

        @app.get("/ping")
        def ping():
            return Response("ok", status=200)

        @app.post("/invocations")
        def invoke():
            if request.mimetype != "text/csv":
                return Response("CSV required", status=415)
            try:
                frame = pd.read_csv(io.StringIO(request.get_data(as_text=True)), header=None)
                if len(frame.columns) != len(bundle["contract"]["features"]):
                    raise ValueError("Wrong feature count")
                frame.columns = bundle["contract"]["features"]
                value = predictions(bundle, frame)
                return Response(pd.DataFrame(value).to_csv(header=False, index=False), mimetype="text/csv")
            except (ValueError, KeyError):
                return Response("Invalid feature contract", status=400)

        from waitress import serve

        serve(app, host="0.0.0.0", port=8080, threads=2)
    else:
        raise SystemExit("Expected train or serve")
