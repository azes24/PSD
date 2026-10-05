import json

cells = []
def _id(): return f"cell-{len(cells):02d}"
def md(s): cells.append({"cell_type": "markdown", "id": _id(), "metadata": {}, "source": s.strip("\n").splitlines(True)})
def code(s): cells.append({"cell_type": "code", "id": _id(), "execution_count": None, "metadata": {}, "outputs": [], "source": s.strip("\n").splitlines(True)})

md("""
# Klasifikasi Sawah vs Non-Sawah menggunakan Sentinel-2A

## Business Understanding

> **"Mengklasifikasikan tutupan lahan menjadi 2 kelas (sawah dan non-sawah) menggunakan citra satelit Sentinel-2A (Level-2A) dengan sampel poligon masing-masing 50 area."**

- **Data:** Citra Sentinel-2 L2A (format GeoTIFF), komposit median tahun 2025
- **Sampel:** 50 poligon sawah (`sawah.zip`) dan 50 poligon non-sawah (`non-sawah.zip`)
- **Kelas:** 2 kelas, `sawah` (1) dan `non-sawah` (0)
- **Metode:** Ekstraksi nilai band/indeks spektral per poligon, lalu klasifikasi supervised (Random Forest, SVM, k-NN)
""")

md("""
## 1. Import Library

Library yang dibutuhkan (install sekali saja jika belum ada):

```
pip install rasterio geopandas scikit-learn matplotlib seaborn pandas numpy requests
```
""")
code("""
import os, zipfile, warnings
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.mask import mask as rio_mask
from rasterio.vrt import WarpedVRT
from rasterio.transform import from_origin
from rasterio.enums import Resampling
import matplotlib.pyplot as plt
import seaborn as sns
import requests

from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from sklearn.neighbors import KNeighborsClassifier
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score

warnings.filterwarnings('ignore')

# Pastikan folder kerja = folder yang berisi sawah.zip (folder data/)
if not os.path.exists('sawah.zip') and os.path.exists(os.path.join('data', 'sawah.zip')):
    os.chdir('data')
print('Folder kerja:', os.getcwd())

BANDS = ["B02", "B03", "B04", "B08", "B11", "B12"]
TIF_PATH = 'sentinel2a_komposit.tif'
NODATA = -32768
""")

md("""
## 2. Data Understanding: Memuat Sampel Poligon

Setiap zip berisi shapefile (`input.shp`, `.shx`, `.dbf`, `.prj`) berisi 50 poligon.
""")
code("""
for nama in ['sawah', 'non-sawah']:
    with zipfile.ZipFile(f'{nama}.zip') as z:
        z.extractall(f'sampel_{nama}')

gdf_sawah = gpd.read_file('sampel_sawah/input.shp').to_crs(4326)
gdf_non = gpd.read_file('sampel_non-sawah/input.shp').to_crs(4326)

gdf_sawah['kelas'] = 'sawah'
gdf_non['kelas'] = 'non-sawah'

gdf = gpd.GeoDataFrame(
    pd.concat([gdf_sawah[['kelas', 'geometry']], gdf_non[['kelas', 'geometry']]], ignore_index=True),
    geometry='geometry', crs=4326)
gdf['label'] = (gdf['kelas'] == 'sawah').astype(int)
gdf['id'] = gdf.index

print('Jumlah sampel sawah    :', (gdf.kelas == 'sawah').sum())
print('Jumlah sampel non-sawah:', (gdf.kelas == 'non-sawah').sum())
print('Luas median poligon (m2):', round(gdf.to_crs(32749).area.median(), 1))
gdf.head()
""")
code("""
# Peta sebaran sampel
ax = gdf.plot(column='kelas', cmap='RdYlGn_r', legend=True, figsize=(8, 8), edgecolor='k')
ax.set_title('Sebaran Sampel Sawah dan Non-Sawah')
plt.show()
""")

md("""
## 3. Crawling Citra Sentinel-2 (GeoTIFF)

Citra diambil dari koleksi **Sentinel-2 L2A** melalui katalog STAC publik *Earth Search* (AWS Open Data), tanpa perlu login. Langkah:

1. Area (bounding box) ditentukan otomatis dari seluruh poligon sampel, lalu diproyeksikan ke UTM 49S (EPSG:32749) dengan resolusi 10 m.
2. Dipilih scene tahun 2025 dengan tutupan awan < 30%.
3. Piksel berawan/bayangan dimasking menggunakan band **SCL** (yang dipertahankan: 4 vegetasi, 5 tanah, 6 air, 7 unclassified).
4. Komposit **median** dari seluruh scene agar bebas awan.
5. Hasil disimpan sebagai **GeoTIFF** 6 band (B02, B03, B04, B08, B11, B12), nilai = reflektansi × 10000.

Jika `sentinel2a_komposit.tif` sudah ada **dan valid**, proses download dilewati.
""")
code("""
def tif_valid(path):
    \"\"\"TIF dianggap valid jika ada, punya 6 band, dan berisi piksel bukan-nodata.\"\"\"
    if not os.path.exists(path):
        return False
    try:
        with rasterio.open(path) as src:
            if src.count < len(BANDS):
                return False
            b = src.read(1)
            nd = src.nodata
            ok = np.isfinite(b) & (b != 0)
            if nd is not None:
                ok &= (b != nd)
            if ok.mean() <= 0.5:
                return False
            # Reflektansi x10000 harus wajar (positif); median negatif = data rusak
            return float(np.median(b[ok])) > 0
    except Exception:
        return False


def grid_target(gdf, pad_m=300, res=10, epsg=32749):
    \"\"\"Grid raster tujuan (UTM 10 m) yang mencakup seluruh sampel.\"\"\"
    minx, miny, maxx, maxy = gdf.to_crs(epsg).total_bounds
    minx = np.floor((minx - pad_m) / res) * res
    miny = np.floor((miny - pad_m) / res) * res
    maxx = np.ceil((maxx + pad_m) / res) * res
    maxy = np.ceil((maxy + pad_m) / res) * res
    width, height = int((maxx - minx) / res), int((maxy - miny) / res)
    return f'EPSG:{epsg}', from_origin(minx, maxy, res, res), width, height


def download_earth_search(gdf, out_path, tanggal=("2025-01-01", "2025-12-31"),
                          max_cloud=30, max_scene=12):
    asset = {"B02": "blue", "B03": "green", "B04": "red", "B08": "nir",
             "B11": "swir16", "B12": "swir22"}
    bbox = [float(v) for v in gdf.to_crs(4326).total_bounds]
    body = {"collections": ["sentinel-2-l2a"], "bbox": bbox,
            "datetime": f"{tanggal[0]}T00:00:00Z/{tanggal[1]}T23:59:59Z",
            "query": {"eo:cloud_cover": {"lt": max_cloud}}, "limit": 100}
    r = requests.post("https://earth-search.aws.element84.com/v1/search", json=body, timeout=120)
    r.raise_for_status()
    items = sorted(r.json()["features"], key=lambda f: f["properties"]["eo:cloud_cover"])[:max_scene]
    if not items:
        raise RuntimeError("Tidak ada scene Sentinel-2 yang ditemukan untuk area & periode ini.")
    print(f"Scene dipakai: {len(items)}")

    crs, transform, width, height = grid_target(gdf)
    vrt_opt = dict(crs=crs, transform=transform, width=width, height=height)

    def baca(href, resampling):
        with rasterio.open(href) as src:
            with WarpedVRT(src, resampling=resampling, **vrt_opt) as vrt:
                return vrt.read(1).astype('float32')

    stack, stack_raw = [], []
    env = dict(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif',
               GDAL_HTTP_MAX_RETRY='5', GDAL_HTTP_RETRY_DELAY='2', AWS_NO_SIGN_REQUEST='YES')
    with rasterio.Env(**env):
        for it in items:
            try:
                scl = baca(it["assets"]["scl"]["href"], Resampling.nearest)
                # Jika offset BOA sudah diterapkan oleh Earth Search, jangan dikurangi lagi
                offset_sudah = bool(it["properties"].get("earthsearch:boa_offset_applied", False))
                cube = []
                for b in BANDS:
                    a = it["assets"][asset[b]]
                    info = (a.get("raster:bands") or [{}])[0]
                    scale = info.get("scale", 0.0001)
                    offset = 0.0 if offset_sudah else info.get("offset", 0.0)
                    dn = baca(a["href"], Resampling.bilinear)
                    refl = np.where(dn > 0, np.clip((dn * scale + offset) * 10000, 0, None), np.nan)
                    cube.append(refl)
                cube = np.stack(cube)
                stack_raw.append(cube.copy())
                cube[:, ~np.isin(scl, [4, 5, 6, 7])] = np.nan
                stack.append(cube)
                print(f"  OK  {it['id']}  awan={it['properties']['eo:cloud_cover']:.1f}%")
            except Exception as e:
                print(f"  SKIP {it['id']}: {e}")
    if not stack:
        raise RuntimeError("Semua scene gagal dibaca. Periksa koneksi internet.")

    med = np.nanmedian(np.stack(stack), axis=0)
    med_raw = np.nanmedian(np.stack(stack_raw), axis=0)
    med = np.where(np.isnan(med), med_raw, med)      # isi piksel yang selalu berawan
    out = np.where(np.isnan(med), NODATA, np.clip(np.round(med), -32767, 32767)).astype('int16')

    profil = dict(driver='GTiff', dtype='int16', count=len(BANDS), nodata=NODATA,
                  compress='deflate', **vrt_opt)
    with rasterio.open(out_path, 'w', **profil) as dst:
        dst.write(out)
        dst.descriptions = tuple(BANDS)
    print('Tersimpan:', out_path)


if tif_valid(TIF_PATH):
    print('TIF sudah ada dan valid, download dilewati.')
else:
    print('TIF belum ada / kosong, mengunduh citra Sentinel-2 ...')
    download_earth_search(gdf, TIF_PATH)

assert tif_valid(TIF_PATH), 'TIF masih tidak valid. Periksa koneksi internet lalu jalankan ulang cell ini.'
""")

md("""
```{note}
Alternatif lain adalah openEO Copernicus Data Space (`openeo.connect("openeo.dataspace.copernicus.eu").authenticate_oidc()`), tetapi cara itu memerlukan login interaktif sehingga tidak bisa dijalankan otomatis saat build Jupyter Book. Karena itu notebook ini memakai Earth Search yang sumber datanya sama (Sentinel-2 L2A).
```
""")
code("""
with rasterio.open(TIF_PATH) as src:
    print('CRS     :', src.crs)
    print('Ukuran  :', src.width, 'x', src.height)
    print('Band    :', src.count, src.descriptions)
    print('Resolusi:', src.res)
    print('dtype   :', src.dtypes[0], '| nodata:', src.nodata)
""")
code("""
def baca_tif(path):
    \"\"\"Baca seluruh band sebagai float, nodata -> NaN.\"\"\"
    with rasterio.open(path) as src:
        arr = src.read().astype('float64')
        if src.nodata is not None:
            arr[arr == src.nodata] = np.nan
        ext = [src.bounds.left, src.bounds.right, src.bounds.bottom, src.bounds.top]
        return arr, src.profile.copy(), ext, src.crs

arr_tif, profil_tif, ext, crs_tif = baca_tif(TIF_PATH)

# Visualisasi True Color (B04, B03, B02); urutan band di TIF: B02,B03,B04,B08,B11,B12
rgb = np.stack([arr_tif[2], arr_tif[1], arr_tif[0]], axis=-1)
rgb = np.clip(rgb / np.nanpercentile(rgb, 98), 0, 1)
rgb = np.nan_to_num(rgb)

fig, ax = plt.subplots(figsize=(9, 9))
ax.imshow(rgb, extent=ext)
gdf_tif = gdf.to_crs(crs_tif)
gdf_tif[gdf_tif.kelas == 'sawah'].boundary.plot(ax=ax, color='lime', linewidth=1.2, label='sawah')
gdf_tif[gdf_tif.kelas == 'non-sawah'].boundary.plot(ax=ax, color='red', linewidth=1.2, label='non-sawah')
ax.legend()
ax.set_title('Sentinel-2 True Color + Sampel')
plt.show()
""")

md("""
## 4. Ekstraksi Fitur

Untuk tiap poligon, diambil seluruh piksel di dalamnya lalu dihitung **rata-rata** tiap band serta indeks spektral:

- **NDVI** = (B08 - B04) / (B08 + B04) : kehijauan vegetasi
- **NDWI** = (B03 - B08) / (B03 + B08) : kadar air (sawah tergenang)
- **NDBI** = (B11 - B08) / (B11 + B08) : area terbangun
- **MNDWI** = (B03 - B11) / (B03 + B11)
- **NDVI_std** : variasi NDVI di dalam poligon (tekstur)
""")
code("""
def ndi(a, b):
    # Normalized difference index; NaN jika penyebut <= 0, hasil dibatasi [-1, 1]
    a = np.asarray(a, dtype='float64')
    b = np.asarray(b, dtype='float64')
    pembagi = a + b
    with np.errstate(divide='ignore', invalid='ignore'):
        hasil = np.where(pembagi > 0, (a - b) / pembagi, np.nan)
    return np.clip(hasil, -1, 1)

baris = []
alasan = {'di luar citra': 0, 'tanpa piksel valid': 0}

with rasterio.open(TIF_PATH) as src:
    gdf_t = gdf.to_crs(src.crs)
    for _, r in gdf_t.iterrows():
        try:
            # filled=False -> MaskedArray, aman untuk dtype int16
            marr, _ = rio_mask(src, [r.geometry], crop=True, filled=False, all_touched=True)
        except ValueError:
            alasan['di luar citra'] += 1
            continue

        arr = np.ma.filled(marr.astype('float64'), np.nan)
        if src.nodata is not None:
            arr[arr == src.nodata] = np.nan

        b02, b03, b04, b08, b11, b12 = arr[:6]
        n_valid = int(np.sum(~np.isnan(b04)))
        if n_valid == 0:
            alasan['tanpa piksel valid'] += 1
            continue

        fitur = {'id': r['id'], 'kelas': r['kelas'], 'label': r['label'], 'n_piksel': n_valid}
        for nama, b in zip(BANDS, arr[:6]):
            fitur[nama] = np.nanmean(b)
        fitur['NDVI'] = np.nanmean(ndi(b08, b04))
        fitur['NDWI'] = np.nanmean(ndi(b03, b08))
        fitur['NDBI'] = np.nanmean(ndi(b11, b08))
        fitur['MNDWI'] = np.nanmean(ndi(b03, b11))
        fitur['NDVI_std'] = np.nanstd(ndi(b08, b04))
        baris.append(fitur)

print('Poligon terekstrak:', len(baris), 'dari', len(gdf))
print('Poligon terlewati :', alasan)
assert len(baris) > 0, 'Tidak ada poligon terekstrak, jalankan ulang cell crawling (bagian 3).'

df = pd.DataFrame(baris).replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)
df.to_csv('fitur_sawah_nonsawah.csv', index=False)
print(df['kelas'].value_counts())
df.head()
""")
code("""
FITUR = BANDS + ['NDVI', 'NDWI', 'NDBI', 'MNDWI', 'NDVI_std']

ringkas = df.groupby('kelas')[FITUR].mean().T
ringkas['selisih (sawah - non-sawah)'] = ringkas['sawah'] - ringkas['non-sawah']
ringkas
""")
code("""
fig, axes = plt.subplots(1, 4, figsize=(18, 4))
for ax, f in zip(axes, ['NDVI', 'NDWI', 'NDBI', 'MNDWI']):
    sns.boxplot(data=df, x='kelas', y=f, hue='kelas',
                palette={'non-sawah': '#d95f02', 'sawah': '#1b9e77'}, legend=False, ax=ax)
    ax.set_title(f)
plt.tight_layout()
plt.show()
""")

md("""
## 5. Klasifikasi 2 Kelas (Sawah vs Non-Sawah)

Data dibagi 80% latih dan 20% uji (stratified), kemudian dibandingkan 3 algoritma. Akurasi juga divalidasi dengan *5-fold cross validation*.
""")
code("""
X = df[FITUR].values
y = df['label'].values

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, stratify=y, random_state=42)

model = {
    'Random Forest': RandomForestClassifier(n_estimators=200, random_state=42),
    'SVM (RBF)': make_pipeline(StandardScaler(), SVC(kernel='rbf', C=10, gamma='scale')),
    'k-NN (k=5)': make_pipeline(StandardScaler(), KNeighborsClassifier(n_neighbors=5)),
}

n_split = int(min(5, np.bincount(y).min()))
cv = StratifiedKFold(n_splits=n_split, shuffle=True, random_state=42)
hasil = []
for nama, m in model.items():
    cv_acc = cross_val_score(m, X, y, cv=cv, scoring='accuracy')
    m.fit(X_train, y_train)
    acc = accuracy_score(y_test, m.predict(X_test))
    hasil.append({'Model': nama, f'CV Akurasi ({n_split}-fold)': cv_acc.mean(),
                  'Std CV': cv_acc.std(), 'Akurasi Test': acc})

tabel_hasil = pd.DataFrame(hasil).sort_values(f'CV Akurasi ({n_split}-fold)', ascending=False)
tabel_hasil
""")
code("""
terbaik = model['Random Forest']
y_pred = terbaik.predict(X_test)

print(classification_report(y_test, y_pred, labels=[0, 1], target_names=['non-sawah', 'sawah'], zero_division=0))

cm = confusion_matrix(y_test, y_pred, labels=[0, 1])
sns.heatmap(cm, annot=True, fmt='d', cmap='Greens',
            xticklabels=['non-sawah', 'sawah'], yticklabels=['non-sawah', 'sawah'])
plt.xlabel('Prediksi'); plt.ylabel('Aktual'); plt.title('Confusion Matrix - Random Forest')
plt.show()
""")
code("""
# Fitur paling berpengaruh
imp = pd.Series(terbaik.feature_importances_, index=FITUR).sort_values()
imp.plot(kind='barh', figsize=(7, 5), color='#1b9e77')
plt.title('Feature Importance - Random Forest')
plt.show()
""")

md("""
## 6. Peta Klasifikasi Seluruh Citra

Model Random Forest dilatih ulang dengan seluruh sampel lalu diterapkan ke setiap piksel GeoTIFF. Fitur `NDVI_std` tidak dipakai di sini karena merupakan statistik per poligon, bukan per piksel.
""")
code("""
FITUR_PETA = BANDS + ['NDVI', 'NDWI', 'NDBI', 'MNDWI']
model_peta = RandomForestClassifier(n_estimators=200, random_state=42).fit(df[FITUR_PETA].values, y)

b02, b03, b04, b08, b11, b12 = arr_tif[:6]
fitur_piksel = np.stack(list(arr_tif[:6]) + [ndi(b08, b04), ndi(b03, b08), ndi(b11, b08), ndi(b03, b11)], axis=-1)

h, w, n = fitur_piksel.shape
flat = fitur_piksel.reshape(-1, n)
valid = np.isfinite(flat).all(axis=1)
peta = np.full(h * w, np.nan)
if valid.any():
    peta[valid] = model_peta.predict(flat[valid])
peta = peta.reshape(h, w)

print(f"Persentase sawah    : {np.nanmean(peta == 1) * 100:.1f}%")
print(f"Persentase non-sawah: {np.nanmean(peta == 0) * 100:.1f}%")

from matplotlib.colors import ListedColormap
fig, ax = plt.subplots(figsize=(9, 9))
im = ax.imshow(peta, cmap=ListedColormap(['#d95f02', '#1b9e77']), vmin=0, vmax=1, extent=ext)
cbar = plt.colorbar(im, ax=ax, ticks=[0.25, 0.75], shrink=0.7)
cbar.ax.set_yticklabels(['non-sawah', 'sawah'])
ax.set_title('Peta Klasifikasi Sawah vs Non-Sawah')
plt.show()
""")
code("""
# Simpan hasil klasifikasi sebagai GeoTIFF (0 = non-sawah, 1 = sawah, 255 = nodata)
profil_out = profil_tif.copy()
profil_out.update(count=1, dtype='uint8', nodata=255, compress='deflate')
peta_out = np.where(np.isnan(peta), 255, peta).astype('uint8')
with rasterio.open('klasifikasi_sawah.tif', 'w', **profil_out) as dst:
    dst.write(peta_out, 1)
print('Tersimpan: klasifikasi_sawah.tif')
""")

md("""
## 7. Kesimpulan

- Sebanyak 50 sampel sawah dan 50 sampel non-sawah diekstraksi dari citra Sentinel-2 L2A (GeoTIFF komposit median 2025).
- Indeks **NDVI**, **NDWI**, dan **NDBI** menjadi pembeda utama antara sawah dan non-sawah (lihat tabel rata-rata dan feature importance).
- Model terbaik dapat dilihat pada tabel perbandingan (bagian 5), lengkap dengan confusion matrix dan peta hasil klasifikasi.
""")

nb = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
      "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
with open('data/klasifikasiSawah.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)
