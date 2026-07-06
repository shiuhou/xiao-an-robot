# Integration Console Visual Trace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 1-2 FPS Route A visual trace to the DK-2500 Integration Console, showing OpenFace landmarks, real Gate diagnostics, and frame-bound asynchronous VLM state.

**Architecture:** The existing `/video` runtime remains the sole owner of decoding, OpenFace, Gate, and VLM execution. A failure-isolated `VisualTracePublisher` observes the already-computed frame data and atomically publishes four ignored runtime artifacts; the Integration Console exposes read-only endpoints and polls them once per second. Real robot verification is a final manual gate, while local packet injection validates the same `/video` code path during development.

**Tech Stack:** Python 3, `unittest`, OpenCV, NumPy, standard-library HTTP server, vanilla HTML/CSS/JavaScript, WebSocket `/video` runtime.

---

## File Map

- Create `base_station/integration_console/visual_trace.py`: landmark projection, overlay rendering, versioned state, atomic image/JSON publishing, VLM lifecycle.
- Create `tests/unit/test_visual_trace.py`: model-free drawing, throttling, atomic publication, and VLM request binding tests.
- Modify `base_station/perception/openface_cv_pipeline.py`: retain the latest raw OpenFace observation as a read-only post-process value.
- Modify `base_station/perception/vlm_trigger_gate.py`: expose diagnostics from the Gate's actual post-evaluation state without re-evaluating.
- Modify `base_station/monitor/emotion_runtime.py`: emit failure-isolated visual observer callbacks around the existing single Gate and VLM calls.
- Modify `tools/ops/run_ws_video_runtime.py`: construct the publisher and add output/FPS CLI options.
- Modify `tests/unit/test_openface_cv_pipeline.py`: verify the observation seam.
- Modify `tests/unit/test_vlm_trigger_gate.py`: verify diagnostics reflect actual thresholds and window counters.
- Modify `tests/unit/test_emotion_runtime.py`: verify observer order, frame binding, and failure isolation.
- Modify `tests/unit/test_run_ws_video_runtime.py`: verify visual publisher CLI wiring.
- Modify `base_station/integration_console/console_server.py`: read visual state and serve annotated/trigger images.
- Modify `tests/unit/test_integration_console_server.py`: verify missing, valid, corrupt, stale, and image endpoint behavior.
- Modify `base_station/integration_console/static/index.html`: replace the simple camera tab with the visual trace layout.
- Modify `base_station/integration_console/static/app.js`: render freshness, CV, Gate, and VLM state keyed by snapshot ID.
- Modify `base_station/integration_console/static/styles.css`: stable desktop and 1024x600 visual trace layout.
- Modify `base_station/integration_console/README.md`: document visual trace files and simulated `/video` workflow.
- Modify `docs/runbooks/integration_console.md`: document simulated and real robot verification plus exact cleanup.

### Task 1: Record Baseline and Expose Real Gate Diagnostics

**Files:**
- Modify: `base_station/perception/vlm_trigger_gate.py`
- Modify: `tests/unit/test_vlm_trigger_gate.py`

- [ ] **Step 1: Run the focused baseline**

Run:

```powershell
python -m unittest tests.unit.test_integration_console_server tests.unit.test_openface_cv_pipeline tests.unit.test_vlm_trigger_gate tests.unit.test_emotion_runtime tests.unit.test_run_ws_video_runtime
```

Expected: existing tests pass before behavior changes. If a test fails, stop and diagnose the baseline instead of changing feature code.

- [ ] **Step 2: Write a failing Gate diagnostics test**

Add a test that evaluates one negative sample, then checks diagnostics without a second `evaluate()` call:

```python
def test_diagnostics_report_actual_thresholds_and_window_state(self) -> None:
    gate = VLMTriggerGate(
        fatigue_threshold=67.0,
        negative_confidence_threshold=0.75,
        window_size=10,
        negative_count_threshold=4,
        negative_conf_sum_threshold=2.0,
    )
    result = gate.evaluate({
        "emotion_tag": "sad",
        "confidence": 0.4,
        "fatigue_score": 20.0,
    })

    diagnostics = gate.diagnostics(sample, result)

    self.assertFalse(result["should_trigger"])
    self.assertEqual(diagnostics["negative_window"]["count"], 1)
    self.assertEqual(diagnostics["negative_window"]["count_threshold"], 4)
    self.assertAlmostEqual(diagnostics["negative_window"]["confidence_sum"], 0.4)
    self.assertEqual(diagnostics["single_negative"]["emotion"], "sad")
    self.assertAlmostEqual(diagnostics["single_negative"]["confidence"], 0.4)
    self.assertEqual(diagnostics["fatigue"]["value"], 20.0)
    self.assertEqual(diagnostics["fatigue"]["threshold"], 67.0)
    self.assertEqual(diagnostics["result"], result)
```

- [ ] **Step 3: Run the test and verify the intended failure**

Run:

```powershell
python -m unittest tests.unit.test_vlm_trigger_gate
```

Expected: FAIL with `AttributeError: 'VLMTriggerGate' object has no attribute 'diagnostics'`.

- [ ] **Step 4: Implement diagnostics without duplicating Gate evaluation**

Add `diagnostics(self, sample, result)` that reads the current sample, configured thresholds, and already-updated deques. It returns display data only and never appends to either deque:

```python
def diagnostics(self, sample: dict, result: dict) -> dict:
    emotion_tag = str(sample.get("emotion_tag", sample.get("emotion", "neutral")) or "neutral")
    confidence = float(sample.get("confidence", 0.0) or 0.0)
    fatigue_score = float(sample.get("fatigue_score", 0.0) or 0.0)
    return {
        "force": {"fired": result.get("reason") == "force"},
        "fatigue": {
            "value": fatigue_score,
            "threshold": self.fatigue_threshold,
            "fired": result.get("reason") == "high_fatigue",
        },
        "single_negative": {
            "emotion": emotion_tag,
            "confidence": confidence,
            "confidence_threshold": self.negative_confidence_threshold,
            "fired": result.get("reason") == "negative_emotion",
        },
        "negative_window": {
            "size": self.window_size,
            "count": sum(self._recent_negative_flags),
            "count_threshold": self.negative_count_threshold,
            "confidence_sum": round(sum(self._recent_negative_confidences), 4),
            "confidence_sum_threshold": self.negative_conf_sum_threshold,
            "fired": result.get("reason") == "negative_emotion_window",
        },
        "result": dict(result),
    }
```

- [ ] **Step 5: Run Gate tests and commit**

Run:

```powershell
python -m unittest tests.unit.test_vlm_trigger_gate
git add base_station/perception/vlm_trigger_gate.py tests/unit/test_vlm_trigger_gate.py
git commit -m "feat: expose VLM gate diagnostics"
```

Expected: tests pass and the commit contains only the Gate and its tests.

### Task 2: Build the Atomic Visual Trace Publisher

**Files:**
- Create: `base_station/integration_console/visual_trace.py`
- Create: `tests/unit/test_visual_trace.py`

- [ ] **Step 1: Write failing projection and publisher tests**

Create model-free tests using a black NumPy image, a four-point observation with `face_bbox=[10, 20, 50, 60]`, and `TemporaryDirectory()`. Assert:

```python
def test_project_landmarks_adds_face_bbox_offset(self) -> None:
    observation = {
        "face_bbox": [10, 20, 50, 60],
        "landmarks": np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32),
    }
    points = project_landmarks_to_frame(observation)
    np.testing.assert_allclose(points, [[11.0, 22.0], [13.0, 24.0]])

def test_publish_writes_only_owned_files_with_matching_snapshot(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        publisher = VisualTracePublisher(temp_dir, max_fps=2.0)
        token = publisher.observe_frame(
            frame=make_frame(7),
            observation=make_observation(),
            cv_sample=make_cv_sample(frame_id=7),
            gate_diagnostics=make_gate_diagnostics(trigger=False),
        )
        state = json.loads((Path(temp_dir) / "latest_state.json").read_text("utf-8"))
        self.assertEqual(state["schema_version"], "visual_console_v1")
        self.assertEqual(state["snapshot_id"], token["snapshot_id"])
        self.assertEqual(state["frame_id"], 7)
        self.assertTrue((Path(temp_dir) / "latest_annotated.jpg").exists())
        self.assertEqual(
            sorted(path.name for path in Path(temp_dir).iterdir()),
            ["latest_annotated.jpg", "latest_state.json"],
        )
```

Also test that a second publication inside the 0.5-second interval is skipped and that a triggering snapshot creates exactly `vlm_trigger.jpg` and `vlm_state.json` in addition to the latest files.

- [ ] **Step 2: Run tests and verify import failure**

Run:

```powershell
python -m unittest tests.unit.test_visual_trace
```

Expected: FAIL because `base_station.integration_console.visual_trace` does not exist.

- [ ] **Step 3: Implement pure projection and rendering helpers**

Implement:

```python
SCHEMA_VERSION = "visual_console_v1"
OWNED_FILENAMES = {
    "latest_annotated.jpg",
    "latest_state.json",
    "vlm_trigger.jpg",
    "vlm_state.json",
}

def project_landmarks_to_frame(observation: dict | None) -> np.ndarray | None:
    if not observation or observation.get("landmarks") is None:
        return None
    points = np.asarray(observation["landmarks"], dtype=np.float32)
    if points.ndim != 2 or points.shape[0] < 98 or points.shape[1] != 2:
        return None
    projected = points.copy()
    bbox = observation.get("face_bbox")
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        projected[:, 0] += float(bbox[0])
        projected[:, 1] += float(bbox[1])
    return projected

def render_annotated_frame(
    frame: dict,
    observation: dict | None,
    cv_sample: dict,
    gate_diagnostics: dict,
) -> np.ndarray:
    payload = frame.get("payload") if isinstance(frame, dict) else None
    if not isinstance(payload, np.ndarray) or payload.ndim != 3:
        raise ValueError("visual trace frame payload must be a BGR image")
    image = payload.copy()
    points = project_landmarks_to_frame(observation)
    if points is None:
        cv2.putText(image, "NO FACE", (12, 28), cv2.FONT_HERSHEY_SIMPLEX,
                    0.65, (0, 200, 255), 2, cv2.LINE_AA)
        return image
    bbox = observation.get("face_bbox") if observation else None
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        x1, y1, x2, y2 = [int(round(float(value))) for value in bbox]
        cv2.rectangle(image, (x1, y1), (x2, y2), (40, 210, 90), 2, cv2.LINE_AA)
    rounded = np.rint(points).astype(np.int32)
    for x, y in rounded:
        cv2.circle(image, (int(x), int(y)), 1, (80, 210, 130), -1, cv2.LINE_AA)
    for indices, color in (
        (WFLW98_RIGHT_EYE, (0, 220, 255)),
        (WFLW98_LEFT_EYE, (0, 220, 255)),
        (WFLW98_OUTER_LIP, (255, 120, 60)),
        (WFLW98_INNER_LIP, (255, 120, 60)),
    ):
        contour = rounded[list(indices)].reshape((-1, 1, 2))
        cv2.polylines(image, [contour], True, color, 2, cv2.LINE_AA)
    frame_id = cv_sample.get("frame_id", frame.get("frame_id", "-"))
    reason = (gate_diagnostics.get("result") or {}).get("reason", "normal")
    cv2.putText(image, f"frame {frame_id} | gate {reason}", (12, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.58, (0, 255, 255), 2, cv2.LINE_AA)
    return image
```

Import `WFLW98_RIGHT_EYE`, `WFLW98_LEFT_EYE`, `WFLW98_OUTER_LIP`, and `WFLW98_INNER_LIP` from `base_station.perception.fatigue.face_metrics`; these are the current production STAR/WFLW indices. Use the existing probe's `face_bbox` projection semantics. Invalid or absent landmarks return the unannotated frame with an explicit `NO FACE` label.

- [ ] **Step 4: Implement atomic publication and throttling**

Implement `VisualTracePublisher(output_dir, max_fps=2.0, wall_clock=None, monotonic_clock=None)` with:

```python
def observe_frame(
    self,
    *,
    frame: dict,
    observation: dict | None,
    cv_sample: dict,
    gate_diagnostics: dict,
) -> dict | None:
    now_monotonic = self.monotonic_clock()
    triggered = bool((gate_diagnostics.get("result") or {}).get("should_trigger"))
    if not triggered and now_monotonic - self._last_published_monotonic < self.min_interval_seconds:
        return None
    image = render_annotated_frame(frame, observation, cv_sample, gate_diagnostics)
    ok, encoded = cv2.imencode(".jpg", image)
    if not ok:
        raise RuntimeError("failed to encode visual trace JPEG")
    published_at_ms = int(self.wall_clock() * 1000)
    frame_id = int(cv_sample.get("frame_id") or frame.get("frame_id") or 0)
    snapshot_id = f"frame-{frame_id}-{published_at_ms}"
    state = self._build_latest_state(
        snapshot_id=snapshot_id,
        frame_id=frame_id,
        published_at_ms=published_at_ms,
        frame=frame,
        observation=observation,
        cv_sample=cv_sample,
        gate_diagnostics=gate_diagnostics,
    )
    jpeg = encoded.tobytes()
    self._atomic_write_bytes(self.output_dir / "latest_annotated.jpg", jpeg)
    self._atomic_write_json(self.output_dir / "latest_state.json", state)
    self._latest_state = state
    self._last_published_monotonic = now_monotonic
    token = {"snapshot_id": snapshot_id, "frame_id": frame_id, "jpeg": jpeg}
    if triggered:
        request_id = f"vlm-{uuid.uuid4().hex[:12]}"
        token["request_id"] = request_id
        self._atomic_write_bytes(self.output_dir / "vlm_trigger.jpg", jpeg)
        self._write_vlm_state(request_id, token, status="queued")
    return token

def vlm_started(self, token: dict, reason: str) -> str | None:
    request_id = token.get("request_id") if isinstance(token, dict) else None
    if not request_id:
        return None
    self._write_vlm_state(request_id, token, status="running", reason=reason)
    return str(request_id)

def vlm_finished(
    self,
    request_id: str | None,
    *,
    status: str,
    vlm_result: dict,
    final_sample: dict | None,
    latency_ms: float,
) -> None:
    if not request_id or request_id != self._active_request_id:
        return
    state = dict(self._vlm_state)
    state.update({
        "status": status,
        "completed_at_ms": int(self.wall_clock() * 1000),
        "latency_ms": round(float(latency_ms), 1),
        "result": self._json_safe(vlm_result),
        "fusion": self._json_safe((final_sample or {}).get("fusion")),
    })
    self._vlm_state = state
    self._atomic_write_json(self.output_dir / "vlm_state.json", state)
    if self._latest_state:
        self._latest_state["vlm"] = dict(state)
        self._atomic_write_json(self.output_dir / "latest_state.json", self._latest_state)
```

Implement the named private helpers in the same class with these fixed responsibilities: `_build_latest_state` constructs JSON-safe `visual_console_v1`; `_atomic_write_bytes` and `_atomic_write_json` write sibling `.tmp` files and call `os.replace`; `_write_vlm_state` updates only the active request; `_json_safe` converts NumPy scalars/arrays and nested containers without serializing the BGR payload.

Encode JPEG in memory with `cv2.imencode`, write sibling `.tmp` files, flush/close them, and publish with `os.replace`. Never enumerate or delete unrelated runtime files.

- [ ] **Step 5: Test success, throttling, errors, and exact ownership**

Run:

```powershell
python -m unittest tests.unit.test_visual_trace
```

Expected: all tests pass without loading OpenFace or VLM models and all test files disappear with their temporary directories.

- [ ] **Step 6: Commit the publisher**

Run:

```powershell
git add base_station/integration_console/visual_trace.py tests/unit/test_visual_trace.py
git commit -m "feat: publish visual trace snapshots"
```

### Task 3: Add a Failure-Isolated Observer to Route A

**Files:**
- Modify: `base_station/perception/openface_cv_pipeline.py`
- Modify: `base_station/monitor/emotion_runtime.py`
- Modify: `tests/unit/test_openface_cv_pipeline.py`
- Modify: `tests/unit/test_emotion_runtime.py`

- [ ] **Step 1: Write the OpenFace observation seam test**

Add a test proving `process_frame()` retains the exact observation object while preserving its existing return contract:

```python
observation = {"landmarks": landmarks, "face_confidence": 0.9, "au": {}}
pipeline = OpenFaceCVPipeline(perceive=lambda frame: observation)
sample = pipeline.process_frame(make_frame())
self.assertIs(pipeline.last_observation, observation)
self.assertIsInstance(sample, dict)
```

- [ ] **Step 2: Write observer lifecycle tests before implementation**

Use a recording observer and assert one normal frame emits only `observe_frame`, while one trigger emits:

```text
observe_frame -> vlm_started -> vlm_finished(done)
```

Add an observer whose every method raises `RuntimeError`; assert the existing source still skips or yields exactly as it did before. Count Gate calls and assert one `evaluate()` per frame.

- [ ] **Step 3: Run tests and verify failures**

Run:

```powershell
python -m unittest tests.unit.test_openface_cv_pipeline tests.unit.test_emotion_runtime
```

Expected: failures for missing `last_observation` and unsupported observer wiring.

- [ ] **Step 4: Retain the observation without changing `cv_sample`**

Initialize `self.last_observation = None` and assign it immediately after `obs = self.perceive(frame) or {}`. Do not add landmarks, EAR, MAR, or face confidence to `cv_sample`.

- [ ] **Step 5: Add observer callbacks around existing work**

Add optional `visual_observer=None` to `VLMGatedCameraEmotionSource`. After the single existing Gate call, obtain diagnostics once and invoke the observer through a catch-all helper:

```python
token = self._observe_visual(
    "observe_frame",
    frame=frame,
    observation=getattr(self.cv_pipeline, "last_observation", None),
    cv_sample=cv_sample,
    gate_diagnostics=self.gate.diagnostics(cv_sample, gate_result),
)
```

On trigger, call `vlm_started`; on success or error, call `vlm_finished`. Observer exceptions are logged when verbose and otherwise ignored. Do not wrap or alter the existing OpenFace, Gate, or VLM exceptions.

Run VLM as one background `asyncio.Task` and wait on that task and the next frame task with `asyncio.wait(..., return_when=asyncio.FIRST_COMPLETED)`. Continue OpenFace/Gate/observer processing while the VLM task is active. If another frame triggers during that interval, retain its Gate diagnostics but do not start or queue another VLM request; only `vlm_started()` may create a request ID and freeze a trigger image.

- [ ] **Step 6: Run focused regressions and commit**

Run:

```powershell
python -m unittest tests.unit.test_openface_cv_pipeline tests.unit.test_vlm_trigger_gate tests.unit.test_emotion_runtime
git add base_station/perception/openface_cv_pipeline.py base_station/monitor/emotion_runtime.py tests/unit/test_openface_cv_pipeline.py tests/unit/test_emotion_runtime.py
git commit -m "feat: observe Route A visual lifecycle"
```

### Task 4: Wire the Publisher into the `/video` Runner

**Files:**
- Modify: `tools/ops/run_ws_video_runtime.py`
- Modify: `tests/unit/test_run_ws_video_runtime.py`

- [ ] **Step 1: Write failing CLI and construction tests**

Assert defaults and injection:

```python
self.assertEqual(args.visual_trace_dir, "runtime/integration_console/visual")
self.assertEqual(args.visual_trace_fps, 2.0)
self.assertFalse(args.no_visual_trace)
```

Patch `VisualTracePublisher`, construct the runtime, and assert the same publisher instance is passed to `VLMGatedCameraEmotionSource`.

- [ ] **Step 2: Verify the tests fail**

Run:

```powershell
python -m unittest tests.unit.test_run_ws_video_runtime
```

Expected: FAIL because visual trace arguments and publisher wiring do not exist.

- [ ] **Step 3: Add minimal runner options and wiring**

Add:

```text
--visual-trace-dir runtime/integration_console/visual
--visual-trace-fps 2.0
--no-visual-trace
```

Construct the publisher unless disabled and pass it to the source. Reject FPS values outside `0.1..2.0` in argument validation so manual commands cannot accidentally create high-frequency disk writes.

- [ ] **Step 4: Run runner and source tests, then commit**

Run:

```powershell
python -m unittest tests.unit.test_run_ws_video_runtime tests.unit.test_emotion_runtime tests.unit.test_ws_video_source
git add tools/ops/run_ws_video_runtime.py tests/unit/test_run_ws_video_runtime.py
git commit -m "feat: publish traces from video runtime"
```

- [ ] **Step 5: Run a simulated `/video` smoke without real models**

Start the runtime in one terminal:

```powershell
python tools/ops/run_ws_video_runtime.py --no-agent --model-backend mock --vlm-backend fake --force-vlm --visual-trace-fps 1
```

Send three generated JPEG frames in a second terminal with the existing sender:

```powershell
python tools/probes/send_test_video_frame.py --url ws://127.0.0.1:8765/video --frames 3 --fps 1 --width 320 --height 240
```

For a real face without adding a repository fixture, pass a user-selected local file outside the repository:

```powershell
python tools/probes/send_test_video_frame.py --url ws://127.0.0.1:8765/video --frames 3 --fps 1 --image-path C:\tmp\visual-trace-face.jpg
```

Expected files, and no others owned by this feature:

```text
runtime/integration_console/visual/latest_annotated.jpg
runtime/integration_console/visual/latest_state.json
runtime/integration_console/visual/vlm_trigger.jpg
runtime/integration_console/visual/vlm_state.json
```

Stop both processes before continuing. Record the exact smoke command in the runbook task.

### Task 5: Add Read-Only Integration Console APIs

**Files:**
- Modify: `base_station/integration_console/console_server.py`
- Modify: `tests/unit/test_integration_console_server.py`

- [ ] **Step 1: Write failing state and endpoint tests**

In `TemporaryDirectory()`, test:

```python
missing = app.visual_state()
self.assertFalse(missing["ok"])
self.assertEqual(missing["reason"], "not_found")
```

Write valid `latest_state.json` and assert `/api/visual/state` returns it with computed `age_ms` and `freshness`. Assert corrupt JSON produces a structured unavailable payload, and missing annotated/trigger images return structured 404 responses.

- [ ] **Step 2: Verify failures**

Run:

```powershell
python -m unittest tests.unit.test_integration_console_server
```

Expected: FAIL because visual methods and routes do not exist.

- [ ] **Step 3: Implement fixed-path readers and routes**

Add a `visual_dir` property fixed to `runtime_dir / "integration_console" / "visual"`. Add:

```text
GET /api/visual/state
GET /api/visual/latest-image
GET /api/visual/trigger-image
```

Use the existing `_load_json_file`, `_file_info`, and `_write_file(no_cache=True)` helpers. Never accept a path query parameter. Mark state `live` at age <= 3000 ms, `stale` above 3000 ms, and `unavailable` when absent or invalid.

- [ ] **Step 4: Run API regression tests and commit**

Run:

```powershell
python -m unittest tests.unit.test_integration_console_server tests.unit.test_dashboard_server
git add base_station/integration_console/console_server.py tests/unit/test_integration_console_server.py
git commit -m "feat: serve visual trace state"
```

### Task 6: Build the Camera Visual Trace Page

**Files:**
- Modify: `base_station/integration_console/static/index.html`
- Modify: `base_station/integration_console/static/app.js`
- Modify: `base_station/integration_console/static/styles.css`
- Modify: `tests/unit/test_integration_console_server.py`

- [ ] **Step 1: Add a failing static contract test**

Fetch `/console` and assert the returned HTML contains stable IDs:

```text
visualLatestImage
visualFreshness
visualCvMetrics
visualGateRules
visualVlmStatus
visualTriggerImage
visualFusion
```

Run the test and expect failure because the current camera tab has only `latestImage`, `imageKv`, and `imageWarn`.

- [ ] **Step 2: Replace only the camera tab layout**

Keep all existing tabs and robot safety controls. Build an un-nested layout with:

- Main annotated image and freshness badge.
- Compact CV metrics row.
- Four Gate rule rows with fixed dimensions.
- VLM trigger thumbnail, request/frame IDs, state, latency, result, and fusion decision.

Do not add threshold inputs or a second command surface.

- [ ] **Step 3: Implement snapshot-keyed polling**

Add a one-second poll to `/api/visual/state`. Update the main image only when `snapshot_id` changes and use a cache-busting query containing that ID. Update the trigger image only when VLM `request_id` changes. Render `live`, `stale`, `unavailable`, `idle`, `running`, `done`, and `error` explicitly.

Render Gate rows from server-provided diagnostics. JavaScript may format values but must not decide whether a rule fired.

- [ ] **Step 4: Add stable responsive styles**

Use a desktop two-column grid with fixed image aspect ratio and compact status rows. At <=900 px stack sections. Ensure long errors and model text wrap without resizing rule rows or overlapping the STOP button.

- [ ] **Step 5: Run tests and browser verification**

Run:

```powershell
python -m unittest tests.unit.test_integration_console_server
python -m base_station.integration_console.console_server --host 127.0.0.1 --port 8090 --runtime-dir runtime
```

Use the in-app browser to verify `/console` at desktop and 1024x600 viewports. Capture screenshots and confirm no overlap, no blank image container when fixtures exist, readable Gate states, and preserved robot controls. Stop the server after verification.

- [ ] **Step 6: Commit the page**

Run:

```powershell
git add base_station/integration_console/static/index.html base_station/integration_console/static/app.js base_station/integration_console/static/styles.css tests/unit/test_integration_console_server.py
git commit -m "feat: show Route A visual trace"
```

### Task 7: Documentation, Cleanup, and Final Verification

**Files:**
- Modify: `base_station/integration_console/README.md`
- Modify: `docs/runbooks/integration_console.md`

- [ ] **Step 1: Document the exact local workflow**

Document three levels separately:

1. Model-free unit tests.
2. Simulated `/video` packet smoke with fake VLM.
3. Real robot `/video` acceptance with real OpenFace and VLM.

State clearly that level 2 validates the production WebSocket packet path but does not prove ESP32 camera/network behavior.

- [ ] **Step 2: Document the real robot procedure without claiming it ran**

Include:

```text
1. Put DK-2500/development PC and robot on the same non-isolated LAN.
2. Determine the base-station IPv4 address with ipconfig.
3. Configure robot WebSocket host to ws://<base-ip>:8765.
4. Start run_ws_video_runtime with openface_ov and the real VLM model path.
5. Start Integration Console on port 8090.
6. Confirm /control hello, /video frame counters, visual state freshness, landmarks, Gate request ID, and VLM completion.
7. If connection fails, check client isolation, Windows firewall inbound TCP 8765, robot serial logs, and runtime/ws_state.json.
```

Do not mark this acceptance complete until the user can provide the robot network.

- [ ] **Step 3: Run focused and broader regressions**

Run:

```powershell
python -m unittest tests.unit.test_visual_trace tests.unit.test_integration_console_server tests.unit.test_openface_cv_pipeline tests.unit.test_vlm_trigger_gate tests.unit.test_emotion_runtime tests.unit.test_run_ws_video_runtime tests.unit.test_ws_video_source
python -m unittest discover -s tests/unit -p "test_*.py"
```

Expected: all focused tests pass. Record any unrelated full-suite failure separately and do not hide it.

- [ ] **Step 4: Perform exact temporary artifact cleanup**

Stop the video runtime and console server. List the feature-owned directory before deletion:

```powershell
Get-ChildItem -Force runtime/integration_console/visual
```

Delete only these known files if present:

```text
latest_annotated.jpg
latest_state.json
vlm_trigger.jpg
vlm_state.json
latest_annotated.jpg.tmp
latest_state.json.tmp
vlm_trigger.jpg.tmp
vlm_state.json.tmp
```

Remove `runtime/integration_console/visual` only if empty. Preserve `runtime/integration_console/events.jsonl`, exports, `runtime/latest.jpg`, audio files, databases, and every unrelated runtime path.

- [ ] **Step 5: Verify repository cleanliness and commit docs**

Run:

```powershell
git status --short
git diff --check
git add base_station/integration_console/README.md docs/runbooks/integration_console.md
git commit -m "docs: document visual trace verification"
```

Expected: no untracked temporary images, JSON, traces, databases, or scripts. Only planned source changes and commits remain.

- [ ] **Step 6: Report the deferred real-hardware gate accurately**

If the robot network remains unavailable, report:

```text
Automated tests: complete
Simulated /video packet path: complete
Real robot /video transport and physical camera: pending user network access
```

Do not call the feature fully hardware-validated until the real robot procedure succeeds.
