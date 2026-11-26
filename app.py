
import os
from pathlib import Path
from urllib.parse import quote

# Atur PROJ sebelum mengimpor GeoPandas
PROJ_PATH = r"C:\anaconda\envs\geospasial\Library\share\proj"
os.environ["PROJ_LIB"] = PROJ_PATH
os.environ["PROJ_DATA"] = PROJ_PATH

import pyproj
pyproj.datadir.set_data_dir(PROJ_PATH)

import streamlit as st
import geopandas as gpd
import folium
import osmnx as ox
import networkx as nx

from shapely.geometry import Point
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster

# --------------------------------------------------
# PENGATURAN HALAMAN
# --------------------------------------------------

st.set_page_config(
    page_title="GeoHealth Surabaya",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data_geohealth"

# Tampilan dashboard
st.markdown("""
<style>
    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2rem;
    }
    [data-testid="stMetric"] {
        background: #f1f6fb;
        padding: 14px;
        border-radius: 12px;
    }
    div.stButton > button {
        border-radius: 9px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# --------------------------------------------------
# MEMUAT DATA SEKALI SAJA
# --------------------------------------------------

@st.cache_data
def load_data():
    batas = gpd.read_file(DATA_DIR / "batas_surabaya.geojson")
    faskes = gpd.read_file(DATA_DIR / "faskes_bersih.geojson")

    batas = batas.to_crs("EPSG:4326")
    faskes = faskes.to_crs("EPSG:4326")

    faskes = faskes.reset_index(drop=True)
    faskes = faskes[
        faskes.geometry.notna() & ~faskes.geometry.is_empty
    ].copy()

    # Peta fasilitas menggunakan titik
    faskes["geometry"] = faskes.geometry.representative_point()

    return batas, faskes


@st.cache_resource
def load_graph():
    graph_path = DATA_DIR / "jaringan_jalan_dengan_waktu.graphml"
    graph = ox.load_graphml(graph_path)

    # Pastikan setiap ruas mempunyai bobot waktu tempuh
    kecepatan_default = {
        "motorway": 60,
        "trunk": 50,
        "primary": 40,
        "secondary": 35,
        "tertiary": 30,
        "residential": 25,
        "unclassified": 25,
        "service": 15
    }

    for u, v, k, data in graph.edges(keys=True, data=True):
        if "travel_time" in data:
            data["travel_time"] = float(data["travel_time"])
        else:
            highway = data.get("highway", "unclassified")

            if isinstance(highway, list):
                highway = highway[0] if highway else "unclassified"

            speed = float(
                data.get("speed_kph", kecepatan_default.get(highway, 25))
            )
            length = float(data.get("length", 0))

            data["travel_time"] = length / (speed * 1000 / 3600)

    return graph


# --------------------------------------------------
# JUDUL
# --------------------------------------------------

st.title("🏥 GeoHealth Surabaya")
st.caption(
    "Sistem Informasi Geografis Persebaran dan Aksesibilitas "
    "Fasilitas Kesehatan Kota Surabaya"
)

try:
    batas, faskes = load_data()

    # --------------------------------------------------
    # SIDEBAR FILTER
    # --------------------------------------------------

    st.sidebar.title("⚙️ Pengaturan Peta")
    st.sidebar.write("Pilih fasilitas yang ingin ditampilkan.")

    semua_jenis = sorted(
        faskes["jenis_faskes"].dropna().unique().tolist()
    )

    jenis_pilihan = st.sidebar.multiselect(
        "Jenis fasilitas kesehatan",
        options=semua_jenis,
        default=semua_jenis
    )

    tampilkan_batas = st.sidebar.checkbox(
        "Tampilkan batas Kota Surabaya",
        value=True
    )

    st.sidebar.divider()
    st.sidebar.caption(
        "GeoHealth Surabaya | Data fasilitas kesehatan OpenStreetMap"
    )

    # Filter data
    faskes_tampil = faskes[
        faskes["jenis_faskes"].isin(jenis_pilihan)
    ].copy()

    # --------------------------------------------------
    # RINGKASAN DATA
    # --------------------------------------------------

    c1, c2, c3 = st.columns(3)

    c1.metric("Total fasilitas", f"{len(faskes):,}")
    c2.metric("Fasilitas ditampilkan", f"{len(faskes_tampil):,}")
    c3.metric("Kategori fasilitas", len(semua_jenis))

    st.divider()

    # --------------------------------------------------
    # LOKASI ASAL PENGGUNA
    # --------------------------------------------------

    st.subheader("📍 Tentukan Lokasi Asal")

    st.info(
        "Klik lokasi pada peta untuk menentukan titik awal perjalanan. "
        "Setelah itu, cari fasilitas kesehatan terdekat."
    )

    if "lokasi_pengguna" not in st.session_state:
        st.session_state["lokasi_pengguna"] = None

    # --------------------------------------------------
    # PETA UTAMA
    # --------------------------------------------------

    peta = folium.Map(
        location=[-7.2575, 112.7378],
        zoom_start=11,
        tiles="OpenStreetMap",
        control_scale=True
    )

    if tampilkan_batas:
        folium.GeoJson(
            batas,
            name="Batas Kota Surabaya",
            style_function=lambda feature: {
                "color": "#1769aa",
                "weight": 2,
                "fillOpacity": 0.03
            }
        ).add_to(peta)

    cluster = MarkerCluster(
        name="Fasilitas Kesehatan"
    ).add_to(peta)

    warna = {
        "Rumah Sakit": "red",
        "Puskesmas": "green",
        "Klinik": "blue",
        "Praktik Dokter": "orange",
        "Fasilitas Kesehatan Lainnya": "purple"
    }

    for _, row in faskes_tampil.iterrows():
        titik = row.geometry
        nama = row.get("name")
        jenis = row.get("jenis_faskes", "Tidak diketahui")

        if nama is None or str(nama).strip() == "":
            nama = "Fasilitas tanpa nama"

        folium.Marker(
            location=[titik.y, titik.x],
            tooltip=str(nama),
            popup=f"<b>{nama}</b><br>Jenis: {jenis}",
            icon=folium.Icon(
                color=warna.get(jenis, "gray"),
                icon="plus-sign",
                prefix="glyphicon"
            )
        ).add_to(cluster)

    # Tampilkan lokasi asal jika sudah dipilih
    lokasi = st.session_state["lokasi_pengguna"]

    if lokasi:
        folium.Marker(
            [lokasi["lat"], lokasi["lon"]],
            tooltip="Lokasi asal kamu",
            popup="Lokasi asal perjalanan",
            icon=folium.Icon(color="darkgreen", icon="home")
        ).add_to(peta)

    folium.LayerControl().add_to(peta)

    hasil_peta = st_folium(
        peta,
        width=None,
        height=570,
        use_container_width=True,
        key="peta_utama",
        returned_objects=["last_clicked"]
    )

    # Simpan titik yang diklik
    if hasil_peta and hasil_peta.get("last_clicked"):
        klik = hasil_peta["last_clicked"]

        titik_baru = {
            "lat": klik["lat"],
            "lon": klik["lng"]
        }

        titik_lama = st.session_state["lokasi_pengguna"]

        if titik_lama != titik_baru:
            st.session_state["lokasi_pengguna"] = titik_baru
            st.session_state.pop("hasil_terdekat", None)
            st.session_state.pop("rute_terpilih", None)
            st.rerun()

    lokasi = st.session_state["lokasi_pengguna"]

    if lokasi:
        st.success(
            f"Lokasi asal dipilih: "
            f"{lokasi['lat']:.5f}, {lokasi['lon']:.5f}"
        )

        if st.button("Hapus lokasi asal"):
            st.session_state["lokasi_pengguna"] = None
            st.session_state.pop("hasil_terdekat", None)
            st.session_state.pop("rute_terpilih", None)
            st.rerun()

    # --------------------------------------------------
    # PENCARIAN FASILITAS TERDEKAT
    # --------------------------------------------------

    st.divider()
    st.subheader("🔎 Fasilitas Kesehatan Terdekat")

    if lokasi:

        if st.button("Cari Fasilitas Terdekat", type="primary"):

            if faskes_tampil.empty:
                st.warning("Tidak ada fasilitas pada kategori yang dipilih.")
            else:
                with st.spinner("Menghitung fasilitas terdekat..."):

                    faskes_meter = faskes_tampil.to_crs("EPSG:32749")

                    titik_asal = gpd.GeoSeries(
                        [Point(lokasi["lon"], lokasi["lat"])],
                        crs="EPSG:4326"
                    ).to_crs("EPSG:32749").iloc[0]

                    jarak = faskes_meter.geometry.distance(titik_asal) / 1000

                    hasil = (
                        faskes_meter.assign(jarak_lurus_km=jarak)
                        .sort_values("jarak_lurus_km")
                        .head(5)
                    )

                    st.session_state["hasil_terdekat"] = hasil.index.tolist()

        hasil_ids = st.session_state.get("hasil_terdekat", [])

        if hasil_ids:
            st.write("**Pilih fasilitas tujuan:**")

            pilihan = st.selectbox(
                "Lima fasilitas terdekat",
                options=hasil_ids,
                format_func=lambda i: (
                    f"{faskes.loc[i, 'name'] if faskes.loc[i, 'name'] else 'Tanpa nama'} "
                    f"— {faskes.loc[i, 'jenis_faskes']}"
                )
            )

            tujuan_row = faskes.loc[pilihan]
            tujuan = tujuan_row.geometry

            st.write(
                f"**Tujuan:** {tujuan_row.get('name') or 'Fasilitas tanpa nama'}"
            )
            st.write(f"**Jenis:** {tujuan_row['jenis_faskes']}")

            if st.button("🧭 Buat Rute Perjalanan", type="primary"):

                with st.spinner("Menghitung rute melalui jaringan jalan..."):

                    G = load_graph()

                    node_awal = ox.distance.nearest_nodes(
                        G,
                        X=lokasi["lon"],
                        Y=lokasi["lat"]
                    )

                    node_tujuan = ox.distance.nearest_nodes(
                        G,
                        X=tujuan.x,
                        Y=tujuan.y
                    )

                    rute = nx.shortest_path(
                        G,
                        source=node_awal,
                        target=node_tujuan,
                        weight="travel_time"
                    )

                    rute_gdf = ox.routing.route_to_gdf(
                        G,
                        rute,
                        weight="travel_time"
                    )

                    jarak_km = rute_gdf["length"].sum() / 1000
                    waktu_menit = rute_gdf["travel_time"].sum() / 60

                    st.session_state["rute_terpilih"] = {
                        "rute": rute_gdf.to_json(),
                        "jarak": jarak_km,
                        "waktu": waktu_menit,
                        "tujuan": pilihan
                    }

        # --------------------------------------------------
        # HASIL RUTE
        # --------------------------------------------------

        data_rute = st.session_state.get("rute_terpilih")

        if data_rute:

            st.divider()
            st.subheader("🗺️ Panduan Rute Perjalanan")

            a, b = st.columns(2)

            a.metric("Jarak perjalanan", f"{data_rute['jarak']:.2f} km")
            b.metric("Estimasi waktu", f"{data_rute['waktu']:.1f} menit")

            rute_gdf = gpd.GeoDataFrame.from_features(
                __import__("json").loads(data_rute["rute"])["features"],
                crs="EPSG:4326"
            )

            peta_rute = folium.Map(
                location=[lokasi["lat"], lokasi["lon"]],
                zoom_start=13,
                tiles="OpenStreetMap"
            )

            folium.Marker(
                [lokasi["lat"], lokasi["lon"]],
                tooltip="Lokasi asal",
                icon=folium.Icon(color="green", icon="home")
            ).add_to(peta_rute)

            folium.Marker(
                [tujuan.y, tujuan.x],
                tooltip="Fasilitas kesehatan tujuan",
                icon=folium.Icon(color="red", icon="plus-sign")
            ).add_to(peta_rute)

            folium.GeoJson(
                rute_gdf.to_json(),
                style_function=lambda feature: {
                    "color": "#1267d5",
                    "weight": 6,
                    "opacity": 0.9
                }
            ).add_to(peta_rute)

            st_folium(
                peta_rute,
                width=None,
                height=500,
                use_container_width=True,
                key="peta_hasil_rute"
            )

            # Daftar nama jalan
            st.markdown("**Jalan yang dilalui:**")

            daftar_jalan = []

            for _, ruas in rute_gdf.iterrows():
                nama_jalan = ruas.get("name")

                if isinstance(nama_jalan, list):
                    nama_jalan = nama_jalan[0] if nama_jalan else None

                if nama_jalan and nama_jalan not in daftar_jalan:
                    daftar_jalan.append(nama_jalan)

            if daftar_jalan:
                for nomor, jalan in enumerate(daftar_jalan, start=1):
                    st.write(f"{nomor}. {jalan}")
            else:
                st.info("Nama jalan tidak tersedia pada data OpenStreetMap.")

            url_maps = (
                f"https://www.google.com/maps/dir/"
                f"{lokasi['lat']},{lokasi['lon']}/"
                f"{tujuan.y},{tujuan.x}/"
            )

            st.link_button(
                "Buka navigasi di Google Maps",
                url_maps
            )

            st.caption(
                "Estimasi waktu berdasarkan kecepatan asumsi jaringan jalan, "
                "bukan kondisi lalu lintas langsung."
            )

    else:
        st.info("Klik lokasi asal pada peta untuk mulai mencari fasilitas kesehatan.")

except Exception as e:
    st.error(f"Terjadi kesalahan: {e}")
    st.exception(e)
