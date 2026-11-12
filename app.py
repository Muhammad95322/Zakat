"""Zakat Insight - Platform SaaS Analitik ZIS untuk Lembaga Zakat Indonesia."""
import sys
from pathlib import Path
import streamlit as st

# Setup Path
BASE_DIR = Path(__file__).parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Log terstruktur tanpa data pribadi + pemantau galat opsional (SENTRY_DSN)
import logging
from src.observabilitas import atur_logging, atur_sentry
atur_logging()
atur_sentry()
logger = logging.getLogger("zakat.app")

# Validasi konfigurasi keamanan sebelum apa pun dijalankan
from src.config import settings, ConfigError
try:
    settings.validate()
except ConfigError as e:
    print(f"[Zakat Insight] Startup dibatalkan: {e}", file=sys.stderr)
    st.error(f"Aplikasi tidak dapat dijalankan karena konfigurasi tidak aman: {e}")
    st.stop()

# Inisialisasi Database saat Startup
try:
    from src.database import init_db
    init_db()
except Exception:
    logger.exception("Gagal inisialisasi basis data")  # detail (host, dll.) hanya di log server
    st.error("Basis data tidak dapat dihubungi. Coba beberapa saat lagi; bila berulang, hubungi admin platform.")
    st.stop()

# Set Page Config
st.set_page_config(
    page_title="Zakat Insight - SaaS Analitik ZIS",
    page_icon="🕌",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Production: tolak akses http (TLS diterminasi proxy Render)
from src.middleware.https import paksa_https
paksa_https()

# Custom Styling Tema Hijau-Teal
st.markdown("""
<style>
    :root {
        --primary-color: #0d9488;
    }
    .stButton>button {
        border-radius: 6px;
    }
</style>
""", unsafe_allow_html=True)

# State Defaults
if "page" not in st.session_state:
    st.session_state["page"] = "login"

def main():
    # Ambil parameter query jika ada (misal token verifikasi)
    query_params = st.query_params
    if query_params.get("page") == "kesehatan":
        st.session_state["page"] = "kesehatan"
    if "token" in query_params:
        target_page = query_params.get("page", "verify_email")
        st.session_state["page"] = target_page

    page = st.session_state.get("page", "login")
    public_pages = {"login", "register", "verify_email", "reset_password", "terima_undangan", "kesehatan"}

    # Otentikasi Gatekeeper
    if page not in public_pages:
        from src.auth.session import is_logged_in, validasi_sesi
        if not is_logged_in() or not validasi_sesi():
            st.session_state["page"] = "login"
            st.rerun()
            return

    # Routing Halaman
    if page == "login":
        from src.pages.pg_login import show
        show()
    elif page == "register":
        from src.pages.pg_register import show
        show()
    elif page == "verify_email":
        from src.pages.pg_verify_email import show
        show()
    elif page == "reset_password":
        from src.pages.pg_reset_password import show
        show()
    elif page == "terima_undangan":
        from src.pages.pg_terima_undangan import show
        show()
    elif page == "kesehatan":
        from src.pages.pg_kesehatan import show
        show()
    elif page == "dashboard":
        from src.components.navbar import show_navbar
        from src.pages.pg_dashboard import show
        show_navbar("dashboard")
        show()
    elif page == "analisis":
        from src.components.navbar import show_navbar
        from src.pages.pg_analisis import show
        show_navbar("analisis")
        show()
    elif page == "upload":
        from src.components.navbar import show_navbar
        from src.pages.pg_upload import show
        show_navbar("upload")
        show()
    elif page == "tim":
        from src.components.navbar import show_navbar
        from src.pages.pg_tim import show
        show_navbar("tim")
        show()
    elif page == "audit":
        from src.components.navbar import show_navbar
        from src.pages.pg_audit import show
        show_navbar("audit")
        show()
    elif page == "langganan":
        from src.components.navbar import show_navbar
        from src.pages.pg_langganan import show
        show_navbar("langganan")
        show()
    elif page == "profil":
        from src.components.navbar import show_navbar
        from src.pages.pg_profil import show
        show_navbar("profil")
        show()
    elif page == "superadmin":
        from src.components.navbar import show_navbar
        from src.pages.pg_superadmin import show
        show_navbar("superadmin")
        show()
    else:
        st.session_state["page"] = "login"
        st.rerun()

if __name__ == "__main__":
    main()

