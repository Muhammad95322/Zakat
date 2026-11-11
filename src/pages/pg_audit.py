"""Halaman Log Audit Jejak Keamanan dan Aktivitas Lembaga."""
import streamlit as st
import pandas as pd
from src.database import get_db
from src.auth.session import get_tenant_id, get_user_role
from src.models.audit_log import AuditLog
from src.models.user import User

def show():
    st.title("📋 Log Audit & Jejak Aktivitas")
    tenant_id = get_tenant_id()
    role = get_user_role()
    
    if role not in ["admin", "super_admin"]:
        st.error("❌ Anda tidak memiliki izin untuk melihat log audit.")
        return

    with get_db() as db:
        query = db.query(AuditLog)
        if role != "super_admin":
            query = query.filter(AuditLog.tenant_id == tenant_id)
        logs = query.order_by(AuditLog.created_at.desc()).limit(100).all()
        
    if not logs:
        st.info("Belum ada log audit yang tercatat.")
        return

    rows = []
    for l in logs:
        rows.append({
            "Waktu": l.created_at.strftime("%d/%m/%Y %H:%M:%S"),
            "Aksi": l.aksi,
            "IP Address": l.ip_address,
            "Detail": str(l.detail)
        })
        
    df_logs = pd.DataFrame(rows)
    st.dataframe(df_logs, use_container_width=True)
    
    # Tombol Ekspor CSV
    from src.ekspor_aman import ke_csv_aman
    csv_bytes = ke_csv_aman(df_logs)
    st.download_button(
        "📥 Ekspor Log ke CSV",
        data=csv_bytes,
        file_name="audit_logs.csv",
        mime="text/csv"
    )

