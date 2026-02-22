from __future__ import annotations
from pathlib import Path
import io
import zipfile
import re
from datetime import datetime

import streamlit as st
from PIL import Image as PILImage

from composer_utils import (
    compose_one_bytes,
    SHADOW_PRESETS,
    has_useful_alpha,
    ensure_rgba,
)


def load_settings():
    try:
        settings = st.secrets.get("settings", {})
        ui = st.secrets.get("ui", {})
        output = st.secrets.get("output", {})

        return {
            "APP_TITLE": settings.get("app_title", "늘보스쿨 Cover Maker"),
            "ACCESS_CODE": settings.get("access_code", "2026"),
            "APP_VERSION": settings.get("app_version", "v1.1"),
            "MAX_PREVIEW_COUNT": int(ui.get("max_preview_count", 50)),
            "GALLERY_COLS": int(ui.get("gallery_columns", 10)),
            "SHOW_MANUAL": ui.get("show_manual_button", True),
            "OUTPUT_FORMAT": output.get("default_format", "JPEG"),
            "JPEG_QUALITY": int(output.get("jpeg_quality", 95)),
        }
    except Exception:
        return {
            "APP_TITLE": "늘보스쿨 Cover Maker",
            "ACCESS_CODE": "2026",
            "APP_VERSION": "v1.1",
            "MAX_PREVIEW_COUNT": 50,
            "GALLERY_COLS": 10,
            "SHOW_MANUAL": True,
            "OUTPUT_FORMAT": "JPEG",
            "JPEG_QUALITY": 95,
        }


CONFIG = load_settings()


@st.dialog("📖 사용 가이드")
def show_manual():
    st.markdown(f"""
    ### 늘보스쿨 Cover Maker

    **[Tip]**
    1. 원클릭으로 대량의 상품 이미지를 여러 샵 템플릿과 합성
    2. 상품 이미지가 투명 배경 PNG인 경우, **배경형/액자형** 템플릿을 동시에 사용 가능
    3. **배경형** 템플릿은 그림자 효과 적용 가능

    **[파일명 생성 규칙]**
    합성된 파일은 다음 규칙으로 파일명 적용
    `(상품 이미지 파일명)_C_(템플릿 이미지 파일명)`
    예시) 상품 이미지 파일명 : SKU0001, 템플릿 이미지 파일명 : SEOUL
    파일명 : `**SKU0001_C_SEOUL**`

    ### 📝 사용법

    1. **상품 이미지 업로드** → 투명 배경 PNG 권장
    2. **템플릿 이미지 업로드** → 배경/액자 이미지
    3. **설정 조정** → 위치, 크기, 그림자 효과
    4. **갤러리 미리보기** → 모든 조합을 한눈에 확인
    5. **생성 & 다운로드** → ZIP 파일로 한번에 다운로드

    ### 🖼️ 이미지 준비 가이드

    **상품 이미지 (Item):**
    - ✅ **투명 배경 PNG** 또는 WEBP
    - ✅ 1000x1000 이상 해상도 권장

    **템플릿 이미지:**
    - **PNG 템플릿**: 액자 모드 (투명한 프레임)
    - **JPG 템플릿**: 배경 모드 (상품 뒤 배경 + 그림자 가능)

    **파일명 규칙:**
    - 영문, 숫자, _, - 만 사용 가능
    - 예: `template_01.png`, `shop-marble.jpg`
    - ❌ 한글, 공백, 특수문자 사용 금지

    """)

    st.divider()
    st.caption(f"늘보스쿨 Cover Maker {CONFIG['APP_VERSION']}")


favicon_path = Path("favicon.png")
if favicon_path.exists():
    page_icon = "favicon.png"
else:
    page_icon = "🌼"

st.set_page_config(
    page_title=CONFIG["APP_TITLE"],
    page_icon=page_icon,
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 세션 상태 초기화
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

# 인증 체크
if not st.session_state["authenticated"]:
    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        sloth_path = Path("sloth_logo.png")
        if sloth_path.exists():
            try:
                sloth_img = PILImage.open(sloth_path)
                st.image(sloth_img, use_column_width=True)
            except Exception:
                st.markdown("""
                <div style="text-align: center; font-size: 80px; margin: 2rem 0;">
                    🌼
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="text-align: center; font-size: 80px; margin: 2rem 0;">
                🌼
            </div>
            """, unsafe_allow_html=True)

        st.markdown("### 🔐 접속 코드")
        with st.form("auth_form"):
            code_input = st.text_input(
                "접속 코드를 입력하세요",
                type="password",
                placeholder="수강생 공지에서 확인하세요"
            )
            submit_btn = st.form_submit_button("입장하기", use_container_width=True)

            if submit_btn:
                if code_input.strip() == CONFIG["ACCESS_CODE"]:
                    st.session_state["authenticated"] = True
                    st.success("✅ 인증 성공! 잠시 후 화면이 열립니다.")
                    st.rerun()
                else:
                    st.error("❌ 코드가 올바르지 않습니다. 다시 확인해주세요.")

        with st.expander("💡 접속 코드는 늘보스쿨 수강생 전용입니다."):
            st.info("""
            접속 코드는 변경될 수 있습니다.
            카카오톡 채팅방의 공지를 확인해주세요. 😊
            """)

    st.stop()

# 헤더
header_col1, header_col2 = st.columns([4, 1])
with header_col1:
    st.title(CONFIG["APP_TITLE"])
    st.caption("상품 커버 자동 합성")
with header_col2:
    if CONFIG["SHOW_MANUAL"]:
        if st.button("📖 사용법", use_container_width=True):
            show_manual()

st.divider()


def validate_template_names(files):
    if not files:
        return True, []

    seen_stems = set()
    errors = []
    pattern = re.compile(r'^[a-zA-Z0-9_-]+$')

    for f in files:
        stem = Path(f.name).stem
        if not pattern.match(stem):
            errors.append(f"'{f.name}' - 영문, 숫자, _, - 만 사용 가능")
            continue
        if stem in seen_stems:
            errors.append(f"'{stem}' - 중복된 템플릿명")
        else:
            seen_stems.add(stem)

    return (False, errors) if errors else (True, [])


def analyze_combinations(item_files, template_files):
    valid_combinations = []
    invalid_combinations = []

    for item_file in item_files:
        try:
            item_file.seek(0)  # 🎯 파일 포인터 초기화
            item_img = PILImage.open(item_file)
            has_alpha = has_useful_alpha(ensure_rgba(item_img))
        except:
            continue

        for template_file in template_files:
            template_ext = Path(template_file.name).suffix.lower()
            is_png_template = (template_ext == '.png')

            if has_alpha:
                mode = 'frame' if is_png_template else 'normal'
                valid_combinations.append((item_file, template_file, mode))
            else:
                if is_png_template:
                    valid_combinations.append((item_file, template_file, 'frame'))
                else:
                    invalid_combinations.append((item_file, template_file))

    return {
        'valid_combinations': valid_combinations,
        'invalid_combinations': invalid_combinations,
        'summary': {
            'valid': len(valid_combinations),
            'invalid': len(invalid_combinations)
        }
    }


# 🎯 최적화된 세션 상태 관리
ss = st.session_state
defaults = {
    "anchor": "center",
    "resize_ratio": 1.0,
    "shadow_preset": "off",
    "preview_list": [],
    "preview_info": [],
    "zip_cache": None,
    "item_uploader_key": 0,
    "template_uploader_key": 0,
    # 🎯 캐싱을 위한 새로운 변수들
    "cached_analysis": None,
    "last_file_sig": None,
    "last_settings_sig": None,
    "needs_preview_regen": False,
}
for k, v in defaults.items():
    ss.setdefault(k, v)

# 메인 레이아웃
left_col, right_col = st.columns([1, 1])

# 왼쪽 컬럼: 이미지 업로드
with left_col:
    st.subheader("📤 이미지 업로드")

    item_files = st.file_uploader(
        "1️⃣ 상품 이미지 (투명 배경 PNG 권장)",
        type=["png", "webp", "jpg", "jpeg"],
        accept_multiple_files=True,
        key=f"item_uploader_{ss.item_uploader_key}",
        help="Remove.bg로 배경을 제거한 PNG 파일이 가장 좋습니다"
    )

    if st.button("🗑️ 상품 이미지 전체 삭제",
                 use_container_width=True,
                 key="clear_items",
                 disabled=not bool(item_files)):
        ss.item_uploader_key += 1
        ss.preview_list = []
        ss.preview_info = []
        ss.zip_cache = None
        # 🎯 캐시 초기화
        ss.cached_analysis = None
        ss.last_file_sig = None
        ss.needs_preview_regen = False
        st.rerun()

    st.markdown("---")

    template_files = st.file_uploader(
        "2️⃣ 템플릿 이미지 (파일명 = 샵코드)",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
        key=f"template_uploader_{ss.template_uploader_key}",
        help="PNG: 액자 모드 자동 적용 / JPG: 배경 모드 자동 적용"
    )

    if st.button("🗑️ 템플릿 이미지 전체 삭제",
                 use_container_width=True,
                 key="clear_templates",
                 disabled=not bool(template_files)):
        ss.template_uploader_key += 1
        ss.preview_list = []
        ss.preview_info = []
        ss.zip_cache = None
        # 🎯 캐시 초기화
        ss.cached_analysis = None
        ss.last_file_sig = None
        ss.needs_preview_regen = False
        st.rerun()

    is_valid_tpl, tpl_errors = validate_template_names(template_files)
    if template_files and not is_valid_tpl:
        st.error("🚨 템플릿 파일명 오류가 발견되었습니다!")
        for err in tpl_errors:
            st.write(f"❌ {err}")
        st.info("💡 파일명을 수정한 후 다시 업로드해주세요.")

    # 🎯 파일 변경 감지 및 분석 캐싱
    if item_files and template_files and is_valid_tpl:
        current_file_sig = (
            tuple(f.name for f in item_files),
            tuple(f.name for f in template_files),
            len(item_files),
            len(template_files)
        )

        # 파일이 변경되었거나 캐시가 없으면 분석 실행
        if ss.last_file_sig != current_file_sig or ss.cached_analysis is None:
            with st.spinner("이미지 분석 중..."):
                ss.cached_analysis = analyze_combinations(item_files, template_files)
                ss.last_file_sig = current_file_sig
                ss.needs_preview_regen = True  # 미리보기 재생성 필요

        # 캐시된 분석 결과 사용
        analysis = ss.cached_analysis
        if analysis:
            summary = analysis['summary']
            if summary['invalid'] > 0:
                st.warning(f"""
                ⚠️ **조합 분석 결과**
                - ✅ 생성 가능: **{summary['valid']}개**
                - ❌ 자동 제외: **{summary['invalid']}개** (투명배경 없음 + JPG 템플릿)
                """)
            else:
                st.success(f"✅ 모든 조합 생성 가능 ({summary['valid']}개)")

# 오른쪽 컬럼: 설정 및 미리보기
with right_col:
    st.subheader("⚙️ 합성 설정")

    c1, c2, c3 = st.columns(3)

    ss.anchor = c1.selectbox(
        "📍 배치 위치",
        ["center", "top", "bottom", "left", "right", "top-left", "top-right", "bottom-left", "bottom-right"],
        index=0
    )

    resize_options = [1.3, 1.2, 1.1, 1.0, 0.9, 0.8, 0.7]
    ss.resize_ratio = c2.selectbox(
        "📏 크기 조정",
        resize_options,
        index=resize_options.index(1.0),
        format_func=lambda x: f"{int(round(x * 100))}%"
    )

    ss.shadow_preset = c3.selectbox(
        "🌑 그림자",
        list(SHADOW_PRESETS.keys()),
        index=0,
        help="JPG 템플릿 + 투명 배경 상품에만 적용됩니다"
    )

    st.divider()

    st.markdown(f"**👁️ 갤러리 미리보기** (최대 {CONFIG['MAX_PREVIEW_COUNT']}개)")

    # 🎯 설정 변경 감지
    current_settings_sig = (ss.anchor, ss.resize_ratio, ss.shadow_preset)
    if ss.last_settings_sig != current_settings_sig:
        ss.needs_preview_regen = True
        ss.last_settings_sig = current_settings_sig

    # 🎯 미리보기 재생성 (필요한 경우에만)
    if item_files and template_files and is_valid_tpl and ss.cached_analysis:
        if ss.needs_preview_regen:
            ss.preview_list = []
            ss.preview_info = []
            ss.zip_cache = None

            valid_combinations = ss.cached_analysis['valid_combinations']
            preview_combinations = valid_combinations[:CONFIG["MAX_PREVIEW_COUNT"]]

            with st.spinner("미리보기 및 다운로드 파일 생성 중..."):
                # 미리보기 생성
                for item_file, template_file, mode in preview_combinations:
                    try:
                        item_file.seek(0)
                        template_file.seek(0)

                        item_img = PILImage.open(item_file)
                        template_img = PILImage.open(template_file)

                        template_ext = Path(template_file.name).suffix.lower()
                        composition_mode = "frame" if template_ext == ".png" else "normal"
                        shadow_preset = ss.shadow_preset if composition_mode == "normal" else "off"

                        opts = {
                            "anchor": ss.anchor,
                            "resize_ratio": ss.resize_ratio,
                            "shadow_preset": shadow_preset,
                            "out_format": "PNG",
                            "composition_mode": composition_mode,
                        }

                        result = compose_one_bytes(item_img, template_img, **opts)
                        if result:
                            ss.preview_list.append(result[0].getvalue())
                            template_name = Path(template_file.name).stem
                            ss.preview_info.append(f"{template_name}")
                    except Exception:
                        pass

                # ZIP 파일 생성
                if valid_combinations:
                    zip_buf = io.BytesIO()
                    count = 0

                    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                        for item_file, template_file, mode in valid_combinations:
                            try:
                                item_file.seek(0)
                                template_file.seek(0)

                                item_img = PILImage.open(item_file)
                                template_img = PILImage.open(template_file)

                                template_ext = Path(template_file.name).suffix.lower()
                                composition_mode = "frame" if template_ext == ".png" else "normal"
                                shadow_preset = ss.shadow_preset if composition_mode == "normal" else "off"

                                opts = {
                                    "anchor": ss.anchor,
                                    "resize_ratio": ss.resize_ratio,
                                    "shadow_preset": shadow_preset,
                                    "out_format": CONFIG["OUTPUT_FORMAT"],
                                    "quality": CONFIG["JPEG_QUALITY"],
                                    "composition_mode": composition_mode,
                                }

                                result = compose_one_bytes(item_img, template_img, **opts)
                                if result:
                                    img_buf, ext = result
                                    item_name = Path(item_file.name).stem
                                    template_code = Path(template_file.name).stem
                                    filename = f"{item_name}_C_{template_code}.{ext}"
                                    zf.writestr(filename, img_buf.getvalue())
                                    count += 1
                            except:
                                pass

                    zip_buf.seek(0)
                    ss.zip_cache = (zip_buf.getvalue(), count, len(valid_combinations) - count)

            # 재생성 완료
            ss.needs_preview_regen = False

        # 갤러리 표시
        if ss.preview_list:
            total_count = len(ss.preview_list)
            cols_per_row = CONFIG["GALLERY_COLS"]

            st.markdown("""
            <style>
            .stImage > img {
                border: 1px solid #e6e6e6;
                border-radius: 4px;
                transition: transform 0.2s;
            }
            .stImage > img:hover {
                transform: scale(1.05);
            }
            </style>
            """, unsafe_allow_html=True)

            for i in range(0, total_count, cols_per_row):
                cols = st.columns(cols_per_row)

                for j, col in enumerate(cols):
                    idx = i + j
                    if idx < total_count:
                        with col:
                            st.image(ss.preview_list[idx], use_column_width=True)
        else:
            st.info("조합 가능한 이미지가 없습니다.")
    else:
        st.info("이미지를 업로드하면 미리보기가 표시됩니다.")

st.divider()

# 다운로드 버튼 (🎯 안정화)
if ss.zip_cache:
    zip_data, success_count, invalid_count = ss.zip_cache

    if success_count > 0:
        st.success(f"✅ 총 {success_count}장 생성 완료!")
        if invalid_count > 0:
            st.info(f"ℹ️ {invalid_count}개 조합은 자동으로 제외되었습니다.")

        now = datetime.now()
        date_time_str = now.strftime("%y%m%d%H%M")
        zip_filename = f"CoverMaker_{date_time_str}.zip"

        # 🎯 안정적인 키 생성
        download_key = f"download_zip_{len(zip_data)}_{success_count}"

        st.download_button(
            label=f"📥 {zip_filename} 다운로드",
            data=zip_data,
            file_name=zip_filename,
            mime="application/zip",
            type="primary",
            use_container_width=True,
            key=download_key,
        )
    else:
        st.error("생성된 이미지가 없습니다. 조합을 확인해주세요.")
elif item_files and template_files and is_valid_tpl:
    st.info("설정을 조정하면 다운로드 파일이 자동으로 생성됩니다.")
else:
    st.info("이미지를 업로드하고 파일명을 확인해주세요.")

st.divider()
st.caption(f"늘보스쿨 Cover Maker {CONFIG['APP_VERSION']}")
