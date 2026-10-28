import re
import json
import random
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st

BASE = Path(__file__).parent
DATA_FILE = BASE / "data" / "scenarios.json"
LOG_FILE = BASE / "logs" / "results.log"

EMAIL_LABELS = {
    "abaikan": "Abaikan pesan",
    "laporkan": "Laporkan sebagai phishing",
    "verifikasi": "Verifikasi lewat kanal resmi",
    "klik_link": "Klik link",
}
LOGIN_LABELS = {
    "masuk": "Tekan tombol Masuk",
    "tutup": "Tutup halaman",
    "periksa_url": "Periksa URL dulu, lalu tutup",
    "laporkan": "Laporkan halaman ini",
}
# Kunci True = skenario phishing, False = skenario sah
EMAIL_POINTS = {
    True: {"abaikan": 3, "laporkan": 5, "verifikasi": 5, "klik_link": 0},
    False: {"abaikan": 1, "laporkan": 0, "verifikasi": 3, "klik_link": 3},
}
LOGIN_POINTS = {
    True: {"masuk": 0, "tutup": 3, "periksa_url": 4, "laporkan": 5},
    False: {"masuk": 3, "tutup": 1, "periksa_url": 3, "laporkan": 0},
}
BATAS_BENAR = 3  # poin keputusan minimal agar dianggap BENAR


# ---------- data, state, log ----------
def load_data():
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        st.error("File skenario hilang atau rusak. Hubungi penyelenggara.")
        st.stop()


def init_state(n):
    if "step" not in st.session_state:
        st.session_state.step = "intro"
        st.session_state.idx = 0
        st.session_state.sid = uuid.uuid4().hex[:6]  # ID acak, bukan nama
        st.session_state.order = random.sample(range(n), n)
        st.session_state.results = []
        st.session_state.cur = {}
        st.session_state.nama = ""


def write_log(sc_id, titik, tindakan, skor, hasil):
    LOG_FILE.parent.mkdir(exist_ok=True)
    baru = not LOG_FILE.exists()
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        if baru:
            f.write("waktu,id_sesi,nama,id_skenario,titik,tindakan,skor,hasil\n")
        waktu = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"{waktu},{st.session_state.sid},{st.session_state.nama},"
                f"{sc_id},{titik},{tindakan},{skor},{hasil}\n")


# ---------- logika scoring ----------
def hitung_indikator(sc, catalog, dipilih):
    ada = set(sc["indicators"])
    dipilih = set(dipilih)
    benar = dipilih & ada
    salah = dipilih - ada          # salah curiga
    terlewat = ada - dipilih
    skor = sum(catalog[k]["bobot"] for k in benar) - len(salah)
    return benar, salah, terlewat, max(0, skor)


def selesai(sc, poin_keputusan, tindakan_akhir):
    cur = st.session_state.cur
    st.session_state.results.append({
        "id": sc["id"],
        "jenis": "phishing" if sc["is_phishing"] else "sah",
        "tindakan": tindakan_akhir,
        "poin_keputusan": poin_keputusan,
        "poin_indikator": cur["skor_ind"],
        "total": poin_keputusan + cur["skor_ind"],
        "benar": poin_keputusan >= BATAS_BENAR,
        "salah": cur["salah"],
        "terlewat": cur["terlewat"],
    })
    st.session_state.step = "feedback"
    st.rerun()


# ---------- halaman ----------
def bersihkan_nama(teks):
    teks = teks.strip()
    if re.fullmatch(r"[A-Za-z0-9_]{2,15}", teks):
        return teks
    return None

def page_intro():
    st.write(
        "Kamu akan melihat beberapa pesan simulasi. Tentukan mana yang mencurigakan "
        "dan apa yang akan kamu lakukan."
    )
    st.info(
        "Semua data di sini simulasi. Jangan memasukkan data asli apa pun. "
        "Jawabanmu dicatat bersama nama panggilan dan ID acak untuk keperluan tugas. "
        "Gunakan nama samaran, bukan nama lengkap asli. "
        "Kamu boleh berhenti kapan saja."
    )
    with st.form("form_nama"):
        nama = st.text_input(
            "Nama panggilan (satu kata, 2-15 huruf/angka):",
            max_chars=15,
        )
        mulai = st.form_submit_button("Mulai", use_container_width=True)
    if mulai:
        bersih = bersihkan_nama(nama)
        if bersih is None:
            st.warning("Nama harus 2-15 karakter, hanya huruf/angka/underscore, tanpa spasi.")
            return
        st.session_state.nama = bersih
        st.session_state.step = "email"
        st.rerun()


def page_email(sc, catalog):
    st.subheader(f"Pesan {st.session_state.idx + 1} dari {len(st.session_state.order)}")
    with st.container(border=True):
        st.markdown(f"**Dari:** {sc['from']}")
        st.markdown(f"**Subjek:** {sc['subject']}")
        st.write(sc["body"])
        st.code(sc["link_text"], language=None)  # teks biasa, bukan link yang bisa diklik

    dipilih = st.multiselect(
        "Indikator mencurigakan yang kamu lihat (boleh kosong):",
        options=list(catalog.keys()),
        format_func=lambda k: catalog[k]["label"],
        key=f"ind_{sc['id']}",
    )
    aksi = st.radio(
        "Apa yang akan kamu lakukan?",
        options=list(EMAIL_LABELS.keys()),
        format_func=lambda k: EMAIL_LABELS[k],
        index=None,
        key=f"aksi_{sc['id']}",
    )
    if st.button("Kirim jawaban"):
        if aksi is None:
            st.warning("Pilih tindakanmu dulu sebelum mengirim.")
            return
        benar, salah, terlewat, skor_ind = hitung_indikator(sc, catalog, dipilih)
        poin = EMAIL_POINTS[sc["is_phishing"]][aksi]
        write_log(sc["id"], "email", aksi, poin, "BENAR" if poin >= BATAS_BENAR else "SALAH")
        st.session_state.cur = {
            "salah": sorted(salah),
            "terlewat": sorted(terlewat),
            "skor_ind": skor_ind,
        }
        if aksi == "klik_link":
            st.session_state.step = "login"
            st.rerun()
        else:
            selesai(sc, poin, aksi)


def page_login(sc):
    st.warning("Kamu mengklik link di pesan tadi, dan halaman ini terbuka.")
    with st.container(border=True):
        st.caption(f"Alamat: {sc['login_url']}")
        st.markdown(f"### {sc['login_title']}")
        if sc.get("login_banner"):
            st.error(sc["login_banner"])
        # Kolom diisi dummy dan dikunci: tidak ada data asli yang bisa diketik
        st.text_input("Username", value="user_dummy", disabled=True, key=f"u_{sc['id']}")
        st.text_input("Password", value="dummy1234", type="password", disabled=True,
                      key=f"p_{sc['id']}")
        st.caption("Simulasi: kolom diisi dummy dan dikunci. Jangan masukkan data asli.")

    aksi = st.radio(
        "Apa yang kamu lakukan di halaman ini?",
        options=list(LOGIN_LABELS.keys()),
        format_func=lambda k: LOGIN_LABELS[k],
        index=None,
        key=f"login_{sc['id']}",
    )
    if st.button("Kirim tindakan"):
        if aksi is None:
            st.warning("Pilih tindakanmu dulu.")
            return
        poin = LOGIN_POINTS[sc["is_phishing"]][aksi]
        write_log(sc["id"], "halaman_login", aksi, poin,
                  "BENAR" if poin >= BATAS_BENAR else "SALAH")
        selesai(sc, poin, aksi)


def page_feedback(sc, catalog):
    r = st.session_state.results[-1]
    if r["benar"]:
        st.success("Keputusanmu tepat.")
    else:
        st.error("Keputusanmu berisiko atau kurang tepat untuk skenario ini.")
    st.write(
        f"Poin keputusan: {r['poin_keputusan']} | Poin indikator: {r['poin_indikator']} "
        f"| **Total: {r['total']}**"
    )
    if r["terlewat"]:
        st.markdown("**Indikator yang terlewat:**")
        for k in r["terlewat"]:
            st.write(f"- {catalog[k]['label']}")
    if r["salah"]:
        st.markdown("**Kamu curiga, tapi indikator ini tidak ada di pesan:**")
        for k in r["salah"]:
            st.write(f"- {catalog[k]['label']}")
    st.info(sc["penjelasan"])
    if st.button("Lanjut"):
        st.session_state.idx += 1
        habis = st.session_state.idx >= len(st.session_state.order)
        st.session_state.step = "end" if habis else "email"
        st.rerun()


def page_end():
    hasil = st.session_state.results
    n_benar = sum(r["benar"] for r in hasil)
    persen = round(100 * n_benar / len(hasil))
    total = sum(r["total"] for r in hasil)
    if persen >= 80:
        kategori = "Waspada"
    elif persen >= 50:
        kategori = "Setengah waspada"
    else:
        kategori = "Berisiko"
    st.subheader(f"Hasil akhir: {kategori}")
    st.write(f"Keputusan tepat: {n_benar} dari {len(hasil)} ({persen}%) | Total skor: {total}")
    st.table([
        {"Skenario": r["id"], "Jenis": r["jenis"], "Tindakan": r["tindakan"],
         "Total": r["total"], "Hasil": "Benar" if r["benar"] else "Salah"}
        for r in hasil
    ])
    if st.button("Ulangi dari awal"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()


# ---------- program utama ----------
def main():
    st.set_page_config(page_title="Phishing Detective")
    data = load_data()
    catalog = data["indikator"]
    skenario = data["skenario"]
    init_state(len(skenario))
    st.title("Phishing Detective")

    step = st.session_state.step
    if step == "intro":
        page_intro()
    elif step == "end":
        page_end()
    else:
        sc = skenario[st.session_state.order[st.session_state.idx]]
        if step == "email":
            page_email(sc, catalog)
        elif step == "login":
            page_login(sc)
        elif step == "feedback":
            page_feedback(sc, catalog)


main()