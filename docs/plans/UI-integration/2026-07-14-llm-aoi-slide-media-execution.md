# LLM AOI, Adjustable Slide, and Media Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan checkpoint-by-checkpoint in goal mode. Do not delegate or create another branch/worktree unless the user explicitly changes the scope. Keep every checkbox and the execution ledger current.

**Goal:** 在现有 `codex/ui-live-runtime-integration-v1` 分支上恢复 Streamlit PDF 缩略图/下载资源、加入 50%–100% 的 slide 显示尺寸调节，并以不覆盖 deterministic AOI 的方式融入 Member 1 的可选 LLM AOI（当前页优先、整份 deck 串行批处理）。

**Architecture:** `/media/*` 重新归 Streamlit，浏览器采集端点迁移到 `/attentive-media/*`；slide iframe 保持满宽，仅缩放 iframe 内部的 `#slide`。LLM AOI 继续使用现有 native subprocess 边界，写入 manifest 的独立 `llm_aois` variant，并由上传 PDF browser 在用户显式启用且 profile 命中时选择；批处理只是对同一单页 worker 的同步串行循环。

**Tech Stack:** Python 3.10, Streamlit 1.59.1, aiohttp, PyMuPDF (`pymupdf`), Pillow, optional EasyOCR, standard-library `urllib` OpenAI-compatible vision calls, HTML/CSS/JavaScript Streamlit custom component, `unittest`.

## Global Constraints

- 实现目录固定为 `/root/autodl-tmp/workspace/AttentiveSlides-ui-live-integration`，直接使用现有分支 `codex/ui-live-runtime-integration-v1`；不创建分支或 worktree。
- Checkpoint 1（media）和 Checkpoint 2（slide size）是必须完成的修复；Checkpoint 3–4 的 LLM AOI 是可选功能，但一旦实现不得破坏 deterministic AOI、Tutor、XAI、live proposal 和 confirmation gate。
- `AOIManager.process_slide(...)` 仍是 deterministic 路径，顶层 `aois` 不得被 LLM 结果覆盖；LLM variant 只写 `llm_aois` 及其有界 metadata。
- API key、Authorization header 和 endpoint credential 不得写入 manifest、日志、UI 或测试快照；错误只保留清洗后的类型/短消息。
- LLM checkbox 与 Tutor cloud-text permission 独立；只有用户勾选 LLM AOI 后，当前页/整 deck 按钮才允许发送 slide image。
- 只处理 uploaded PDF；built-in fixture deck 不提供 LLM AOI。
- 整 deck 只允许逐页同步处理：不加线程、并发 API、队列、数据库、daemon、取消协议或自动上传后处理。
- 不新增依赖；保留 `RLock`、atomic manifest replace、`children`、`allow_ocr=False`、DPI-qualified image filenames 和现有 public methods。
- embedded-image OCR 只在 `allow_ocr=True` 时执行；关闭 OCR 不妨碍用户显式将整页图像发送给 VLM。
- 测试预算：每个 checkpoint 末尾只跑一组 focused tests；中间最多执行一次预期失败的 focused run；全量 suite 只在 Checkpoint 4 最后跑一次；浏览器 smoke 只做一次。
- 真实 LLM acceptance 最多处理一页 text-heavy 和一页 visual-heavy slide；其余 automated tests 一律使用 fake response/generator/worker。
- 禁止顺手重构、改 Tutor prompt、改模型选择、加 gaze/calibration/object detection、drag resize 或新 AOI hierarchy。

## File/Interface Map

| File | Responsibility in this plan |
|---|---|
| `scripts/run_live_single_port.py` | Proxy origin selection: `/capture` and `/attentive-media/*` → ingress; `/media/*` → Streamlit. |
| `modules/media/single_port_transport.py` | Capture HTML fetch URLs and aiohttp ingress routes under `/attentive-media/*`. |
| `modules/system/main_ui_state.py` | Slide-width normalization and `MainUISlide.aoi_profile` state contract. |
| `modules/ui/slide_viewport_component/__init__.py` | Clamp/pass `display_width_percent` to the component. |
| `modules/ui/slide_viewport_component/index.html` | Center and resize internal `#slide`, preserving normalized manual bbox and actual geometry reporting. |
| `modules/slide/llm_aoi.py` | Member 1 VLM request/response validation plus non-secret profile fingerprint and sanitized configuration state. |
| `modules/slide/slide_parser.py` | Embedded PDF image bbox extraction; preserve current import style and DPI filenames. |
| `modules/slide/ocr.py` | Region OCR with normalized crop-to-page coordinate remapping. |
| `modules/slide/aoi_manager.py` | Deterministic anchors, reconciliation, cache profile, separate `llm_aois`, fallback metadata, and effective AOI selection. |
| `scripts/pdf_native_worker.py` | New `prepare-llm-aoi` subprocess action and bounded JSON summary. |
| `modules/system/uploaded_deck_service.py` | Invoke/reload native worker; expose current-page LLM state/preparation and sequential deck preparation. |
| `modules/system/real_slide_provider.py` | Permit `llm_guided` only through an explicit LLM selection path and order new AOI types. |
| `apps/streamlit_attentive_slides.py` | Sidebar opt-in/batch UI, current-page toolbar action, profile activation reset, and slide-size slider. |
| `tests/test_llm_aoi.py` | Fake VLM validation, profile, reconciliation, manifest preservation, stale/fallback tests. |
| Existing focused tests | Routing, component geometry, workspace/worker/provider, UI contracts, batch continuation. |

---

## Checkpoint 1: Restore Streamlit media and PDF thumbnails

**Deliverable:** `/media/<hash>.*` and download assets are proxied to Streamlit, while browser capture continues to work under `/attentive-media/*` and `/capture`.

**Files:**

- Modify: `scripts/run_live_single_port.py:48-49`
- Modify: `modules/media/single_port_transport.py:349-676`
- Modify: `tests/test_live_single_port_launcher.py`
- Modify: `tests/test_single_port_transport.py`

**Interfaces:**

- Consumes: `select_origin(path: str, streamlit_origin: str, ingress_origin: str) -> str`
- Produces: capture namespace `/attentive-media/{start,video,audio,heartbeat,stop,stats}`; `/capture` remains ingress; `/media/*` becomes ordinary Streamlit traffic.

- [ ] **Step 1.1: Record checkpoint start in the handoff log and confirm scope**

```bash
cd /root/autodl-tmp/workspace/AttentiveSlides-ui-live-integration
git status --short --branch
```

Expected: branch is `codex/ui-live-runtime-integration-v1`; only approved documentation changes may already exist. Do not stash, reset, or create a branch.

- [ ] **Step 1.2: Change the focused routing tests first**

Update `tests/test_live_single_port_launcher.py` so the origin contract is explicit:

```python
def test_capture_routes_use_private_namespace_and_streamlit_media_stays_streamlit(self):
    from scripts.run_live_single_port import select_origin

    streamlit = "http://127.0.0.1:8502"
    ingress = "http://127.0.0.1:8503"
    self.assertEqual(select_origin("/capture", streamlit, ingress), ingress)
    self.assertEqual(
        select_origin("/attentive-media/video", streamlit, ingress),
        ingress,
    )
    self.assertEqual(select_origin("/media/thumbnail.jpg", streamlit, ingress), streamlit)
    self.assertEqual(select_origin("/_stcore/stream", streamlit, ingress), streamlit)
    self.assertEqual(select_origin("/", streamlit, ingress), streamlit)
```

Update the proxy integration test to POST `/attentive-media/heartbeat`, assert ingress saw that path, and GET `/media/thumbnail.jpg`, asserting `streamlit:/media/thumbnail.jpg`.

Update `tests/test_single_port_transport.py` expected route set and HTML strings:

```python
expected_capture_paths = {
    "/attentive-media/start",
    "/attentive-media/video",
    "/attentive-media/audio",
    "/attentive-media/heartbeat",
    "/attentive-media/stop",
    "/attentive-media/stats",
}
self.assertTrue(expected_capture_paths.issubset(paths))
self.assertNotIn("/media/video", paths)
self.assertIn('fetch("/attentive-media/video"', page)
self.assertIn('fetch("/attentive-media/audio"', page)
```

- [ ] **Step 1.3: Run the single expected-red checkpoint test group**

```bash
/root/miniconda3/envs/attentive-app/bin/python -m unittest \
  tests.test_live_single_port_launcher \
  tests.test_single_port_transport -v
```

Expected before implementation: failures mention the old `/media/*` capture routing. Do not run unrelated tests here.

- [ ] **Step 1.4: Implement the namespace move**

Replace the selector with this exact boundary:

```python
def select_origin(path: str, streamlit_origin: str, ingress_origin: str) -> str:
    is_capture_path = path == "/capture" or path.startswith("/attentive-media/")
    return ingress_origin if is_capture_path else streamlit_origin
```

In `fallback_page_html()`, change all six request URLs and the unload beacon from `/media/...` to `/attentive-media/...`. In `build_fallback_app(...)`, register exactly:

```python
app.router.add_post("/attentive-media/start", start)
app.router.add_post("/attentive-media/video", video)
app.router.add_post("/attentive-media/audio", audio)
app.router.add_post("/attentive-media/heartbeat", heartbeat)
app.router.add_post("/attentive-media/stop", stop)
app.router.add_get("/attentive-media/stats", stats)
```

Keep `/capture`, `/health`, and `/` unchanged. Do not add aliases for the old `/media/*` capture endpoints because aliases would recreate the collision.

- [ ] **Step 1.5: Run only the checkpoint test group**

```bash
/root/miniconda3/envs/attentive-app/bin/python -m unittest \
  tests.test_live_single_port_launcher \
  tests.test_single_port_transport -v
```

Expected: all tests in both modules pass; `/media/thumbnail.jpg` is observed at the Streamlit fake origin.

- [ ] **Step 1.6: Review and commit Checkpoint 1**

```bash
git diff --check
git diff -- scripts/run_live_single_port.py modules/media/single_port_transport.py tests/test_live_single_port_launcher.py tests/test_single_port_transport.py
git add scripts/run_live_single_port.py modules/media/single_port_transport.py tests/test_live_single_port_launcher.py tests/test_single_port_transport.py docs/plans/UI-integration/handoffs/llm-aoi-slide-media-log.md
git commit -m "fix: restore Streamlit media routing"
```

Checkpoint gate: stop if `/media/*` still appears as a capture route or if `/capture` no longer reaches ingress. Update the handoff log with test count and commit hash.

---

## Checkpoint 2: Adjustable slide width with stable geometry

**Deliverable:** a compact `Slide size` slider accepts 50–100 in steps of 5; the iframe stays full-width, internal slide content is centered at the selected percentage, and AOI/manual/viewport geometry remains normalized to the actual image.

**Files:**

- Modify: `modules/system/main_ui_state.py`
- Modify: `modules/ui/slide_viewport_component/__init__.py`
- Modify: `modules/ui/slide_viewport_component/index.html`
- Modify: `apps/streamlit_attentive_slides.py`
- Modify: `tests/test_main_ui_state.py`
- Modify: `tests/test_slide_geometry.py`
- Modify: `tests/test_compact_main_layout.py`
- Modify: `tests/test_streamlit_attentive_slides.py`

**Interfaces:**

- Produces: `normalize_main_slide_width_percent(value: object) -> int`
- Changes: `render_slide_viewport(..., display_width_percent: int, ...) -> dict[str, object] | None`
- Session contract: `main_slide_width_percent`, default `100`, range `50..100`, step `5`.

- [ ] **Step 2.1: Add focused contract tests**

In `tests/test_main_ui_state.py`:

```python
def test_slide_width_is_clamped_and_snapped(self):
    from modules.system.main_ui_state import normalize_main_slide_width_percent

    self.assertEqual(normalize_main_slide_width_percent(None), 100)
    self.assertEqual(normalize_main_slide_width_percent(49), 50)
    self.assertEqual(normalize_main_slide_width_percent(73), 75)
    self.assertEqual(normalize_main_slide_width_percent(101), 100)
```

In `tests/test_slide_geometry.py`, patch the declared component and assert `display_width_percent=75` is passed; add static HTML assertions:

```python
self.assertIn("margin-inline: auto", html)
self.assertIn("display_width_percent", html)
self.assertIn("slide.style.width", html)
self.assertIn("image.getBoundingClientRect()", html)
```

Keep the existing `same render preserves manual bbox` assertion. Add an assertion that width changes do not participate in `preserveManualBBox` reset identity; deck, slide, drawing mode and explicit `layout_revision` remain the reset inputs.

In layout/UI AST tests, require one slider with key `main_slide_width_percent`, label `Slide size`, values `50`, `100`, `5`, and require it to appear immediately before `render_slide_viewport` in `_render_slide_workspace`.

- [ ] **Step 2.2: Run the single expected-red checkpoint group**

```bash
/root/miniconda3/envs/attentive-app/bin/python -m unittest \
  tests.test_main_ui_state \
  tests.test_slide_geometry \
  tests.test_compact_main_layout \
  tests.test_streamlit_attentive_slides -v
```

Expected before implementation: new helper/argument/slider assertions fail. Do not run the full suite.

- [ ] **Step 2.3: Add normalization and global session state**

Add to `modules/system/main_ui_state.py`:

```python
def normalize_main_slide_width_percent(value: object) -> int:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 100
    snapped = int(round(numeric / 5.0) * 5)
    return max(50, min(100, snapped))
```

Import it in `apps/streamlit_attentive_slides.py`. Add `"main_slide_width_percent": 100` to `_initialize_global_state()` and normalize it in `_normalize_widget_state()`:

```python
st.session_state["main_slide_width_percent"] = normalize_main_slide_width_percent(
    st.session_state.get("main_slide_width_percent")
)
```

Do not put this preference in `build_main_turn_defaults()`; resetting a learning turn must not restore the slide to 100%.

- [ ] **Step 2.4: Pass the width through the Python component boundary**

Change the wrapper signature and clamp again at the boundary:

```python
def render_slide_viewport(
    *,
    deck_id: str,
    slide: MainUISlide,
    layout_revision: int,
    drawing_enabled: bool,
    show_aoi_overlay: bool,
    display_width_percent: int,
    key: str,
) -> dict[str, object] | None:
    # existing guards/image encoding remain unchanged
    bounded_width = max(50, min(100, int(display_width_percent)))
    value: Any = _component()(
        # existing args remain unchanged
        display_width_percent=bounded_width,
        default=None,
        key=key,
    )
```

In `_render_slide_workspace(view)`, render and pass the preference without an `on_change` callback:

```python
st.slider(
    "Slide size",
    min_value=50,
    max_value=100,
    step=5,
    key="main_slide_width_percent",
    help="Resize the displayed slide while preserving normalized AOI geometry.",
)

payload = render_slide_viewport(
    # existing args
    display_width_percent=int(st.session_state["main_slide_width_percent"]),
    # existing key
)
```

- [ ] **Step 2.5: Center and resize only internal `#slide`**

Change CSS to:

```css
#root { width: 100%; }
#slide {
  position: relative;
  width: 100%;
  margin-inline: auto;
  line-height: 0;
  user-select: none;
}
#slide img { display: block; width: 100%; height: auto; border-radius: 12px; }
```

In `render(nextArgs)`, after creating `slide`, apply the bounded argument:

```javascript
const requestedWidth = Number(args.display_width_percent);
const displayWidth = Math.max(50, Math.min(100, Number.isFinite(requestedWidth) ? requestedWidth : 100));
slide.style.width = `${displayWidth}%`;
```

Do not add width to `sameSlideIdentity`, `lastRequestedRevision`, or the manual bbox reset decision. Keep `report()` based on `image.getBoundingClientRect()` so `slide_rect`, `aoi_rects`, and pixel dimensions reflect the resized image.

- [ ] **Step 2.6: Run only the checkpoint test group**

```bash
/root/miniconda3/envs/attentive-app/bin/python -m unittest \
  tests.test_main_ui_state \
  tests.test_slide_geometry \
  tests.test_compact_main_layout \
  tests.test_streamlit_attentive_slides -v
```

Expected: all pass. Do not start a browser yet; the single browser smoke is reserved for Checkpoint 4.

- [ ] **Step 2.7: Review and commit Checkpoint 2**

```bash
git diff --check
git add modules/system/main_ui_state.py modules/ui/slide_viewport_component/__init__.py modules/ui/slide_viewport_component/index.html apps/streamlit_attentive_slides.py tests/test_main_ui_state.py tests/test_slide_geometry.py tests/test_compact_main_layout.py tests/test_streamlit_attentive_slides.py docs/plans/UI-integration/handoffs/llm-aoi-slide-media-log.md
git commit -m "feat: add adjustable slide width"
```

Checkpoint gate: turn reset must preserve width, pure width change must preserve normalized manual bbox, and the component iframe/root must remain 100% width. Record focused results and commit hash.

---

## Checkpoint 3: Current-page LLM AOI variant, cache, fallback, and activation

**Deliverable:** for an uploaded PDF, an explicit checkbox and toolbar button can prepare the current slide through one native worker; successful `llm_aois` load from cache, failures retain deterministic `aois`, and AOI universe changes clear stale turn/live state.

**Files:**

- Create: `modules/slide/llm_aoi.py`
- Create: `tests/test_llm_aoi.py`
- Modify: `modules/slide/slide_parser.py`
- Modify: `modules/slide/ocr.py`
- Modify: `modules/slide/aoi_manager.py`
- Modify: `scripts/pdf_native_worker.py`
- Modify: `modules/system/uploaded_deck_service.py`
- Modify: `modules/system/real_slide_provider.py`
- Modify: `modules/system/main_ui_state.py`
- Modify: `apps/streamlit_attentive_slides.py`
- Modify: `tests/test_uploaded_deck_service.py`
- Modify: `tests/test_real_slide_provider.py`
- Modify: `tests/test_aoi_manager_concurrency.py`
- Modify: `tests/test_main_ui_widget_inventory.py`
- Modify: `tests/test_streamlit_attentive_slides.py`

**Interfaces:**

- `LLMAOIConfig.from_env() -> LLMAOIConfig`
- `LLMAOIGenerator.profile(anchor_digest: str) -> str`
- `LLMAOIGenerator.is_configured() -> bool`
- `LLMAOIGenerator.generate(image_path: str, slide_text: str, rule_aois: list[dict[str, Any]], text_aois: list[dict[str, Any]]) -> list[dict[str, Any]]`
- `SlideParser.extract_pdf_image_boxes(deck_id: str, slide_id: int) -> list[list[float]]`
- `OCREngine.extract_region_boxes(image_path: str, region: list[float], min_confidence: float = 0.25) -> list[TextBox]`
- `AOIManager.process_llm_aoi(deck_id: str, slide_id: int, *, dpi: int = 250, allow_ocr: bool = True, force: bool = False) -> dict[str, Any]`
- `AOIManager.get_llm_aoi_state(deck_id: str, slide_id: int) -> dict[str, Any]`
- `AOIManager.get_effective_aois(deck_id: str, slide_id: int, *, use_llm_aoi: bool) -> tuple[list[dict[str, Any]], str]`
- `UploadedDeckWorkspace.prepare_llm_aoi(deck_id: str, slide_id: int, *, force: bool = False) -> dict[str, Any]`
- `UploadedDeckWorkspace.get_llm_aoi_state(deck_id: str, slide_id: int) -> dict[str, Any]`
- `UploadedDeckWorkspace.open_browser(deck_id: str, *, use_llm_aoi: bool = False) -> UploadedDeckBrowser`
- `MainUISlide.aoi_profile: str`, default `"deterministic"`.

- [ ] **Step 3.1: Add fake-only LLM unit and integration tests**

Create `tests/test_llm_aoi.py` with small PNG fixtures and an injected fake generator. Cover these exact cases:

```python
class FakeLLMGenerator:
    def __init__(self, *, result=None, error=None, profile="profile-a"):
        self.result = result or []
        self.error = error
        self.calls = 0
        self.config = SimpleNamespace(model="fake-vlm")
        self._profile = profile

    def is_configured(self):
        return True

    def profile(self, anchor_digest):
        return f"{self._profile}:{anchor_digest}"

    def generate(self, image_path, slide_text, rule_aois, text_aois):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return list(self.result)
```

Tests must assert:

1. malformed/empty/invalid bbox response is rejected;
2. duplicate text is removed and IDs become `llm_aoi_1..N`;
3. insufficient text coverage falls back, while a valid visual-heavy result with few anchors is accepted;
4. success writes `llm_aois`, `used`, model/profile, no secret, and preserves the old top-level `aois` byte-for-byte;
5. timeout/malformed output writes `fallback_used`, sanitized error, and preserves deterministic AOIs;
6. same successful profile is cached with zero additional fake calls unless `force=True`;
7. changed deterministic anchor digest makes old LLM data ineligible and `get_effective_aois` returns deterministic;
8. effective LLM AOIs include `whole_slide` even when the model omitted it;
9. `allow_ocr=False` never calls region OCR;
10. deterministic save keeps a matching variant and marks a mismatched one stale;
11. existing manifest concurrency test still serializes writes.

Add workspace/worker tests using a patched `_run_native_worker`, never a real HTTP call. Assert the command begins with `prepare-llm-aoi` and that the workspace reloads `AOIManager` before reading the result.

- [ ] **Step 3.2: Run the single expected-red checkpoint group**

```bash
/root/miniconda3/envs/attentive-app/bin/python -m unittest \
  tests.test_llm_aoi \
  tests.test_uploaded_deck_service \
  tests.test_real_slide_provider \
  tests.test_aoi_manager_concurrency \
  tests.test_main_ui_state \
  tests.test_main_ui_widget_inventory \
  tests.test_streamlit_attentive_slides -v
```

Expected before implementation: missing module/method/UI contract failures. This is the only red run for Checkpoint 3.

- [ ] **Step 3.3: Import Member 1 VLM behavior as an isolated module**

Port `member1/modules/slide/llm_aoi.py` at audited commit `263a604`, preserving standard-library HTTP and validation behavior. Add a stable schema constant and non-secret profile:

```python
PROMPT_SCHEMA_VERSION = "attentive-llm-aoi-v1"

def profile(self, anchor_digest: str) -> str:
    payload = {
        "model": self.config.model,
        "prompt_schema": PROMPT_SCHEMA_VERSION,
        "max_image_side": self.config.max_image_side,
        "anchor_digest": anchor_digest,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
```

The profile payload must not contain endpoint or API key. Keep the allowed type set and map model confidence to `group_confidence`. Keep the prompt flat: no parent/child/container AOIs, image as visual truth, PDF/OCR AOIs as anchors.

Expose only sanitized configuration errors to callers:

```python
def sanitized_llm_error(error: Exception) -> str:
    message = " ".join(str(error).split())
    return f"{type(error).__name__}: {message[:240]}"
```

Do not include request headers, full response bodies, endpoint query strings, or environment values in that message.

Keep the existing `AOIManager(data_dir)` call valid while allowing fake injection in tests:

```python
def __init__(
    self,
    data_dir: str = "data",
    *,
    llm_aoi_generator: LLMAOIGenerator | None = None,
) -> None:
    # existing data_dir/manifest/RLock initialization
    self.llm_aoi_generator = llm_aoi_generator or LLMAOIGenerator()
```

- [ ] **Step 3.4: Merge only the Member 1 parser/OCR helpers**

Add `SlideParser.extract_pdf_image_boxes(...)` using `page.get_text("dict")` image blocks (`type == 1`), normalized bbox, area `0.002..0.75`, and footer-asset exclusion. Keep current:

```python
image_path = self.images_dir / f"{deck_id}_slide_{slide_id:03d}_{dpi}dpi.png"
```

Add `OCREngine.extract_region_boxes(...)` using a temporary cropped PNG and remapping local normalized boxes into page coordinates. Import `NamedTemporaryFile`; close Pillow images through context managers. Its returned `TextBox.source` must be `"ocr_image"`.

- [ ] **Step 3.5: Add separate LLM storage/reconciliation without changing deterministic output**

Keep `process_slide(...)` signature and output. Selectively port these Member 1 helpers into the current locked manager:

```python
extract_image_text_boxes(...)
build_image_region_aois(...)
merge_text_boxes(...)
merge_pdf_wrapped_aois(...)
build_llm_guided_aois(...)
reconcile_llm_aois(...)
```

Call image-region OCR only inside the deterministic preparation branch guarded by `allow_ocr`. Preserve `children` when creating/merging deterministic semantic AOIs.

Use a canonical anchor digest over stable fields only:

```python
def _anchor_digest(self, slide_data: dict[str, Any]) -> str:
    anchors = [
        {
            "aoi_id": str(aoi.get("aoi_id", "")),
            "bbox": [round(float(v), 6) for v in aoi.get("bbox", [])],
            "type": str(aoi.get("type", "")),
            "text": " ".join(str(aoi.get("text", "")).split()),
        }
        for aoi in slide_data.get("aois", [])
        if aoi.get("source") in {"pdf_text_semantic", "ocr", "ocr_image"}
    ]
    raw = json.dumps(anchors, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
```

Implement `process_llm_aoi(...)` with this order:

1. ensure/prepare deterministic slide with the requested DPI/OCR flag;
2. derive anchor digest and expected profile;
3. return cached record only when `status == "used"`, profile matches, and `force is False`;
4. call generator with complete rendered image, slide text, coarse rule AOIs, and deterministic anchor AOIs;
5. reconcile and reject empty/invalid/duplicate/insufficient-coverage output;
6. under the existing `RLock`, update only `llm_aois`, `llm_aoi_status`, `llm_aoi_model`, `llm_aoi_profile`, `llm_aoi_error` and atomically save;
7. on exception, set `fallback_used`, empty `llm_aois`, sanitized error, and return the preserved deterministic record.

Implement effective selection:

```python
def get_effective_aois(self, deck_id: str, slide_id: int, *, use_llm_aoi: bool) -> tuple[list[dict[str, Any]], str]:
    slide_data = self._ensure_slide_data(deck_id, slide_id)
    state = self.get_llm_aoi_state(deck_id, slide_id)
    if use_llm_aoi and state["eligible"]:
        selected = [dict(aoi) for aoi in slide_data.get("llm_aois", [])]
        profile = str(slide_data["llm_aoi_profile"])
    else:
        selected = [dict(aoi) for aoi in slide_data.get("aois", [])]
        profile = "deterministic"
    if not any(aoi.get("aoi_id") == "whole_slide" for aoi in selected):
        selected.append(self.generate_rule_aois(str(slide_data.get("ocr_text", "")))[-1].to_dict())
    return selected, profile
```

`get_llm_aoi_state(...)` is read-only and must not call the model. It returns this stable UI/service shape:

```python
{
    "configured": bool,
    "status": "not_requested" | "used" | "fallback_used",
    "model": str | None,
    "profile": str | None,
    "expected_profile": str | None,
    "eligible": bool,
    "aoi_count": int,
    "error": str | None,
}
```

`eligible` is true only for configured, `used`, non-empty `llm_aois`, and stored profile equal to the profile currently derived from model/schema/max-image-side/current anchor digest.

When deterministic data is saved, compare the new anchor digest with the stored profile input/digest metadata. Preserve a matching LLM variant; otherwise set status to `not_requested`, clear eligibility, and retain no stale active result.

- [ ] **Step 3.6: Extend the native worker and workspace boundary**

Add `prepare_llm_aoi(...)` to `scripts/pdf_native_worker.py` and a `prepare-llm-aoi` argparse action with existing data/deck/slide/DPI/OCR args plus `--force`. Return only:

```python
return {
    "deck_id": deck_id,
    "slide_id": slide_id,
    "status": slide_data.get("llm_aoi_status", "fallback_used"),
    "model": slide_data.get("llm_aoi_model"),
    "profile": slide_data.get("llm_aoi_profile"),
    "aoi_count": len(slide_data.get("llm_aois", [])),
    "error": slide_data.get("llm_aoi_error"),
}
```

In `UploadedDeckWorkspace.prepare_llm_aoi(...)`, build one worker invocation, append `--enable-ocr` from `ATTENTIVE_ENABLE_OCR`, append `--force` only for explicit retry, run with the existing 300-second timeout/stderr-tail path, reload `AOIManager`, and return `get_llm_aoi_state(...)`.

Change the uploaded browser boundary without triggering LLM work during navigation or thumbnails:

```python
def open_browser(self, deck_id: str, *, use_llm_aoi: bool = False) -> UploadedDeckBrowser: ...

def get_slide(self, deck_id: str, slide_id: int, *, use_llm_aoi: bool = False) -> MainUISlide:
    slide_data = self._get_or_process_slide(deck_id, slide_id)  # deterministic only
    raw_aois, aoi_profile = self.aoi_manager.get_effective_aois(
        deck_id, slide_id, use_llm_aoi=use_llm_aoi
    )
    # existing AOI conversion/neighbor/image behavior
    return MainUISlide(..., aois=aois, image_path=image_path or None, aoi_profile=aoi_profile)
```

Store `use_llm_aoi` on `UploadedDeckBrowser` and pass it only to `workspace.get_slide`. Seven thumbnail `get_slide` calls must never call `prepare_llm_aoi`.

- [ ] **Step 3.7: Make explicit LLM selection compatible with providers/state**

Add `aoi_profile: str = "deterministic"` to `MainUISlide` and its `to_dict()` output.

In `RealSlideProvider`, add priorities for `diagram`, `table`, `formula`, and `code`, accept source `llm_guided` only when `get_slide_frame(..., use_llm_aoi=True)` explicitly selects valid `llm_aois`, and key its frame cache by `(slide_id, use_llm_aoi)`. Deterministic calls must still choose only `pdf_text_semantic`/`ocr` with rule fallback.

- [ ] **Step 3.8: Add uploaded-deck opt-in and current-page toolbar UI**

Add defaults:

```python
"main_llm_aoi_enabled": False,
"main_active_aoi_signature": None,
"main_llm_aoi_message": None,
"main_llm_aoi_error": None,
```

For uploaded decks only, render this sidebar checkbox before `_resolve_active_browser(...)`:

```python
st.sidebar.checkbox(
    "Enable LLM AOI (send slide images to the configured cloud model)",
    key="main_llm_aoi_enabled",
    on_change=_on_llm_aoi_mode_change,
)
```

The callback calls `_reset_turn_state()` and clears `main_active_aoi_signature`; it must not change `main_cloud_text_allowed`.

Resolve uploaded browser with:

```python
workspace.open_browser(
    deck_id,
    use_llm_aoi=bool(st.session_state.get("main_llm_aoi_enabled")),
)
```

After building `view` and before binding live resources, compare:

```python
signature = f"{view.deck_id}:{view.active_slide_id}:{view.active_slide.aoi_profile}"
if st.session_state.get("main_active_aoi_signature") != signature:
    _reset_turn_state()
    st.session_state["main_active_aoi_signature"] = signature
```

This clears selected IDs, proposals, confirmation, Tutor/XAI output and increments canvas revision whenever the effective AOI universe changes.

Above the slide-size slider, render current-page action only when uploaded + checkbox enabled:

- eligible success: disabled `LLM AOIs loaded`;
- `fallback_used`: `Retry current slide with LLM`, invokes `force=True` only on click;
- otherwise: `Process current slide with LLM`, invokes `force=False`;
- unconfigured: disabled action plus `LLM AOI is not configured`;
- worker/result error: `st.error` with sanitized message, deterministic AOIs stay active;
- success: reset turn state and `st.rerun()` exactly once so cached LLM AOIs become active.

Use static keys `main_llm_aoi_enabled`, `main_process_current_llm_aoi`, and register the checkbox callback in widget-inventory tests.

- [ ] **Step 3.9: Run only the Checkpoint 3 focused group**

```bash
/root/miniconda3/envs/attentive-app/bin/python -m unittest \
  tests.test_llm_aoi \
  tests.test_uploaded_deck_service \
  tests.test_real_slide_provider \
  tests.test_aoi_manager_concurrency \
  tests.test_main_ui_state \
  tests.test_main_ui_widget_inventory \
  tests.test_streamlit_attentive_slides -v
```

Expected: all fake-only tests pass; no network call; concurrency and existing deterministic provider tests remain green.

- [ ] **Step 3.10: Review security/state diff and commit Checkpoint 3**

```bash
git diff --check
git grep -n -E "Authorization|API_KEY" -- modules/slide modules/system apps/streamlit_attentive_slides.py
git add modules/slide/llm_aoi.py modules/slide/slide_parser.py modules/slide/ocr.py modules/slide/aoi_manager.py scripts/pdf_native_worker.py modules/system/uploaded_deck_service.py modules/system/real_slide_provider.py modules/system/main_ui_state.py apps/streamlit_attentive_slides.py tests/test_llm_aoi.py tests/test_uploaded_deck_service.py tests/test_real_slide_provider.py tests/test_aoi_manager_concurrency.py tests/test_main_ui_state.py tests/test_main_ui_widget_inventory.py tests/test_streamlit_attentive_slides.py docs/plans/UI-integration/handoffs/llm-aoi-slide-media-log.md
git commit -m "feat: integrate optional current-slide LLM AOI"
```

Expected grep: environment-variable names/config code may appear; no literal credential and no code that writes key/header/endpoint to manifest. Checkpoint gate: disabling the checkbox immediately selects deterministic AOIs; failure/retry never removes top-level `aois`. Record test results and commit hash.

---

## Checkpoint 4: Sequential deck batch and final acceptance

**Deliverable:** sidebar batch button processes ascending page IDs one at a time, skips profile-matching successes, continues after fallbacks, reports counts, and the four-checkpoint result passes one final suite and one browser smoke.

**Files:**

- Modify: `modules/system/uploaded_deck_service.py`
- Modify: `apps/streamlit_attentive_slides.py`
- Modify: `tests/test_uploaded_deck_service.py`
- Modify: `tests/test_main_ui_widget_inventory.py`
- Modify: `tests/test_streamlit_attentive_slides.py`
- Update during execution only: `docs/plans/UI-integration/handoffs/llm-aoi-slide-media-log.md`

**Interfaces:**

- Produces: `UploadedDeckWorkspace.prepare_llm_deck(deck_id: str, *, progress_callback: Callable[[int, int, dict[str, Any]], None] | None = None) -> dict[str, int]`
- Summary keys: `successful`, `fallback`, `skipped`, `total`.

- [ ] **Step 4.1: Add fake sequential batch tests**

Patch `prepare_llm_aoi`/state reads and assert exact ascending call order, no concurrency, cached skip, and continuation:

```python
def test_llm_deck_batch_is_sequential_skips_success_and_continues_fallback(self):
    events = []
    # page 1 is eligible/cached, page 2 returns fallback, page 3 returns used
    summary = workspace.prepare_llm_deck(
        deck_id,
        progress_callback=lambda completed, total, result: events.append(
            (completed, total, result["slide_id"], result["status"])
        ),
    )
    self.assertEqual(processed_slide_ids, [2, 3])
    self.assertEqual([event[2] for event in events], [1, 2, 3])
    self.assertEqual(
        summary,
        {"successful": 1, "fallback": 1, "skipped": 1, "total": 3},
    )
```

UI/AST tests must require sidebar button key `main_process_deck_llm_aoi`, page-count/sequential caption, progress update, and final summary copy. Assert the button is absent/disabled for built-in deck and disabled when the LLM checkbox is off.

- [ ] **Step 4.2: Run the single expected-red checkpoint group**

```bash
/root/miniconda3/envs/attentive-app/bin/python -m unittest \
  tests.test_uploaded_deck_service \
  tests.test_main_ui_widget_inventory \
  tests.test_streamlit_attentive_slides -v
```

Expected before implementation: missing batch method/button failures only.

- [ ] **Step 4.3: Implement the synchronous service loop**

Use page IDs from `1..get_page_count(deck_id)` and never create a thread/executor:

```python
def prepare_llm_deck(self, deck_id, *, progress_callback=None):
    total = self.slide_parser.get_page_count(deck_id)
    counts = {"successful": 0, "fallback": 0, "skipped": 0, "total": total}
    for completed, slide_id in enumerate(range(1, total + 1), start=1):
        state = self.get_llm_aoi_state(deck_id, slide_id)
        if state.get("eligible"):
            result = {**state, "slide_id": slide_id, "status": "skipped"}
            counts["skipped"] += 1
        else:
            result = self.prepare_llm_aoi(deck_id, slide_id, force=True)
            result = {**result, "slide_id": slide_id}
            if result.get("status") == "used":
                counts["successful"] += 1
            else:
                counts["fallback"] += 1
        if progress_callback is not None:
            progress_callback(completed, total, result)
    return counts
```

If deterministic preparation or worker invocation raises, convert that page to a sanitized fallback result inside this loop, increment `fallback`, call the progress callback, and continue. Do not swallow `KeyboardInterrupt`/`SystemExit`.

- [ ] **Step 4.4: Add the sidebar batch controls**

When an uploaded deck is active and LLM AOI is enabled, show:

```python
st.sidebar.caption(
    f"{browser.page_count} pages will be processed sequentially; cached successful pages are skipped."
)
batch_clicked = st.sidebar.button(
    "Process entire deck with LLM",
    key="main_process_deck_llm_aoi",
    width="stretch",
)
```

On click, create one `st.sidebar.progress(0.0)` and one `st.sidebar.empty()` caption placeholder. The callback updates `completed / total` and the progress fraction. After completion, report exactly:

```python
st.sidebar.success(
    "LLM AOI deck processing finished: "
    f"{summary['successful']} successful, "
    f"{summary['fallback']} fallback, "
    f"{summary['skipped']} skipped."
)
```

Then call `_reset_turn_state()`, clear `main_active_aoi_signature`, and `st.rerun()` once. Do not automatically navigate slides and do not automatically start the batch when the checkbox is toggled.

- [ ] **Step 4.5: Run the Checkpoint 4 focused group**

```bash
/root/miniconda3/envs/attentive-app/bin/python -m unittest \
  tests.test_uploaded_deck_service \
  tests.test_main_ui_widget_inventory \
  tests.test_streamlit_attentive_slides -v
```

Expected: all pass with fake workers and deterministic call order.

- [ ] **Step 4.6: Run the one permitted final full suite**

```bash
/root/miniconda3/envs/attentive-app/bin/python -m unittest discover -s tests -v
```

Expected: exit code 0. If failures occur, fix only regressions caused by these four checkpoints, rerun the failing module(s), then rerun the full suite once after the fixes. Record commands and counts in the handoff log.

- [ ] **Step 4.7: Perform one final browser smoke session**

Start the single-port launcher on the audited live ports (stop the old process first if those ports are already occupied):

```bash
cd /root/autodl-tmp/workspace/AttentiveSlides-ui-live-integration
/root/miniconda3/envs/attentive-app/bin/python scripts/run_live_single_port.py \
  --host 0.0.0.0 --port 18601 \
  --streamlit-host 127.0.0.1 --streamlit-port 18602 \
  --ingress-host 127.0.0.1 --ingress-port 18603
```

In that one session verify:

1. Upload a PDF with at least 3 pages; all visible thumbnails have `naturalWidth > 0` and no `/media/*` 404 appears in browser console/network.
2. A Streamlit download/media asset still works through the public port.
3. Set `Slide size` to `50`, `75`, and `100`; image is centered; AOI overlay and a manual rectangle remain aligned; reported viewport geometry follows actual image bounds.
4. Draw a manual bbox, change only slide size, and confirm normalized selection persists; navigate/reset and confirm it clears.
5. With LLM checkbox off, deterministic AOIs and existing Tutor behavior are unchanged.
6. With checkbox on, process one current page, observe one worker call, rerun/load cached `llm_aois`, navigate away/back without another API call, then uncheck and return immediately to deterministic AOIs.
7. Trigger one controlled fake/missing-config failure and confirm deterministic AOIs/navigation remain available and retry copy is shown.
8. Run a short multi-page batch; confirm ascending sequential progress, cached skip, fallback continuation and final counts.

If real credentials are configured, use at most one text-heavy and one visual-heavy page across steps 6–8. Do not paste keys or response bodies into the log.

- [ ] **Step 4.8: Final diff audit and commit**

```bash
git diff --check
git status --short
git diff --stat
git add modules/system/uploaded_deck_service.py apps/streamlit_attentive_slides.py tests/test_uploaded_deck_service.py tests/test_main_ui_widget_inventory.py tests/test_streamlit_attentive_slides.py docs/plans/UI-integration/handoffs/llm-aoi-slide-media-log.md
git commit -m "feat: add sequential deck LLM AOI processing"
```

Do not push unless the user separately authorizes it.

Final acceptance gate:

- `/media/*` belongs to Streamlit; `/attentive-media/*` belongs to capture ingress.
- slide width 50/75/100 keeps overlays/manual/geometry aligned.
- deterministic top-level `aois` survives LLM success, timeout, malformed output, missing config and worker crash.
- matching LLM cache is reused; stale profile/anchor data is not activated; `whole_slide` always exists.
- batch is ascending, synchronous, skip-success, continue-on-fallback, with accurate counts.
- full suite and the one browser smoke are recorded; no new dependency/service/branch/worktree/queue/database exists.

---

## Goal-Mode Stop/Resume Protocol

At the end of every checkpoint:

1. update `docs/plans/UI-integration/handoffs/llm-aoi-slide-media-log.md` with completed checkboxes, files, exact verification output summary, commit hash, and next checkpoint;
2. ensure `git status --short` contains no unaccounted product changes;
3. stop for review if the checkpoint gate fails—do not expand scope to compensate;
4. on resume, read the spec, this plan, and the handoff log, then continue from the first unchecked step;
5. never repeat a passing full suite or browser smoke just to create more evidence.
