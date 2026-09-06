# Implementasi Analisis Data Polutan Gresik: Dari CSV ke Cloud Database (Aiven) hingga KNIME

**Dataset:** `Polutan_Gresik_Terkini.csv`
**Periode:** 2025-09-01 s.d. 2026-08-30 (363 baris data harian)
**Variabel:** `NO2`, `CO`, `SO2`, `O3` (konsentrasi harian gas polutan)

Panduan ini menguraikan alur kerja *end-to-end*: memindahkan data *time-series* polutan dari file CSV menuju database PostgreSQL di platform **Aiven**, menginspeksinya lewat **pgAdmin 4 / HeidiSQL**, lalu menariknya ke **KNIME Analytics Platform** untuk dihitung statistika deskriptifnya. Setiap metrik pada node **Statistics** dijelaskan besertaan rumus dan contoh perhitungan manual memakai data asli pada dataset ini.

---

## Bagian 1 — Memindahkan Data Time Series ke PostgreSQL (Aiven)

### Langkah 1: Menyiapkan Service PostgreSQL di Aiven
1. Masuk ke *dashboard* **Aiven**, buat proyek baru (atau gunakan yang sudah ada), lalu buat *service* **PostgreSQL**.
2. Setelah *service* aktif (status *Running*), buka tab **Overview** dan catat kredensial koneksi:
   * **Host**, **Port**, **User** (`avnadmin`), **Password**, **SSL mode** (`require`).
3. Buat database khusus, misalnya `db_polutan_gresik`, melalui tab **Databases**.

### Langkah 2: Menghubungkan & Membuat Tabel via pgAdmin 4
1. Buka **pgAdmin 4** → klik kanan **Servers** → **Register → Server...**.
2. Tab **General**: beri nama koneksi, misal `Aiven Polutan Gresik`.
3. Tab **Connection**: isi Host, Port, Maintenance database (`db_polutan_gresik`), Username (`avnadmin`), dan Password dari Langkah 1, centang **Save password?**, lalu **Save**.
4. Buat tabel `polutan_gresik` dengan skema yang menyesuaikan struktur CSV:

```sql
CREATE TABLE polutan_gresik (
    date DATE PRIMARY KEY,
    no2  DOUBLE PRECISION,
    co   DOUBLE PRECISION,
    so2  DOUBLE PRECISION,
    o3   DOUBLE PRECISION
);
```

### Langkah 3: Mengimpor Data CSV ke Tabel
1. Pada pgAdmin, klik kanan tabel `polutan_gresik` → **Import/Export Data...**.
2. Pilih mode **Import**, arahkan *Filename* ke `Polutan_Gresik_Terkini.csv`, format `csv`, centang **Header**, delimiter `,`.
3. Petakan kolom CSV (`date, NO2, CO, SO2, O3`) ke kolom tabel (`date, no2, co, so2, o3`), lalu jalankan.
4. Verifikasi: klik kanan tabel → **View/Edit Data → All Rows**. Sel kosong pada CSV (mis. baris `2025-09-07` dan `2025-09-08`) akan tampil sebagai `[null]` — inilah *missing values* yang nantinya terhitung otomatis pada tahap statistik.

> Alternatif *tanpa* GUI: gunakan `psql \copy` atau *client* seperti HeidiSQL/DBeaver dengan mekanisme yang sama (koneksi → buat tabel → import CSV).

---

## Bagian 2 — Menarik Data ke KNIME Analytics Platform

### Langkah 4: Menyusun Workflow di KNIME
1. Buat *workflow* baru, lalu tambahkan *node* berikut dari *Node Repository*:
   * **PostgreSQL Connector** — menghubungkan KNIME ke server Aiven.
   * **DB Table Selector** — memilih skema `public` dan tabel `polutan_gresik`.
   * **DB Reader** — memuat data ke memori KNIME.
   * **Statistics** — menghitung metrik statistika deskriptif.
2. Hubungkan node secara berurutan: `PostgreSQL Connector → DB Table Selector → DB Reader → Statistics`.
3. Konfigurasi **PostgreSQL Connector**: isi Hostname, Port, Database name (`db_polutan_gresik`), serta kredensial (User/Password) sama seperti Langkah 1–2.
4. Konfigurasi **DB Table Selector**: pilih skema `public`, tabel `polutan_gresik`.
5. Eksekusi **DB Reader** (klik kanan → **Execute**); indikator hijau menandakan data berhasil dimuat.

### Langkah 5: Menjalankan Node Statistics
1. Klik kanan node **Statistics** → **Execute**, lalu setelah hijau, pilih **Statistics View**.
2. Tabel output akan memuat kolom `no2`, `co`, `so2`, `o3` dengan metrik: **Min, Max, Mean, Std. deviation, Variance, Skewness, Kurtosis, Overall Sum, No. missings, No. NaNs, No. +infs/-infs**, serta histogram sebaran tiap kolom.

Berikut ringkasan nilai aktual dari dataset `Polutan_Gresik_Terkini.csv` (dihitung terhadap baris valid, tidak termasuk *missing*):

| Metrik | NO2 | CO | SO2 | O3 |
|---|---|---|---|---|
| n valid (dari 363) | 288 | 275 | 307 | 360 |
| No. missings | 75 | 88 | 56 | 3 |
| Min | 6.195e-06 | 0.021424 | -0.000615 | 0.110516 |
| Max | 1.957e-04 | 0.042927 | 0.000575 | 0.122790 |
| Mean | 4.458e-05 | 0.029244 | 5.339e-05 | 0.115819 |
| Median | 4.023e-05 | 0.028893 | 4.926e-05 | 0.115645 |
| Std. Deviation | 2.188e-05 | 0.003242 | 1.394e-04 | 0.002362 |
| Variance | 4.789e-10 | 1.051e-05 | 1.943e-08 | 5.578e-06 |
| Skewness | 1.849 | 0.842 | -0.365 | 0.430 |
| Kurtosis (excess) | 7.919 | 1.781 | 4.479 | -0.132 |
| Overall Sum | 0.012840 | 8.042181 | 0.016392 | 41.694804 |

**Interpretasi cepat:** `NO2` paling menceng ke kanan (skewness 1.85) dan paling *leptokurtik* (kurtosis 7.92) → banyak nilai ekstrem tinggi yang jarang muncul. `O3` paling mendekati simetris dan sedikit *platikurtik* (kurtosis -0.13) → puncak distribusinya relatif datar. `SO2` memiliki nilai negatif (karena berasal dari data satelit yang bisa menghasilkan bias koreksi negatif) sehingga skewness-nya negatif (-0.365).

---

## Bagian 3 — Penjelasan Setiap Fitur pada Node Statistics: Rumus & Contoh Perhitungan Manual

Contoh perhitungan manual di bawah ini menggunakan kolom **`CO`** (n valid = 275, dari total 363 baris dikurangi 88 *missing*).

### 1. Min & Max
**Penjelasan:** Nilai observasi terendah (Min) dan tertinggi (Max) dalam data — menunjukkan rentang sebaran nilai.

**Rumus:**
$$Min = X_1 \qquad Max = X_n$$
*(setelah data diurutkan dari terkecil ke terbesar)*

**Contoh (CO):** Setelah 275 nilai `CO` valid diurutkan,
$$Min_{CO} = 0.021424 \qquad Max_{CO} = 0.042927$$

### 2. Mean
**Penjelasan:** Nilai rata-rata; dihitung dengan menjumlahkan seluruh observasi valid lalu dibagi jumlah observasi tersebut.

**Rumus:**
$$\bar{x} = \frac{\sum_{i=1}^{n} x_i}{n}$$

**Contoh (CO):**
$$n = 363 - 88 = 275$$
$$\bar{x}_{CO} = \frac{8.042181}{275} = 0.029244$$

### 3. Std. Deviation
**Penjelasan:** Mengukur rata-rata simpangan data terhadap Mean. Nilai rendah → data konsisten/mengelompok; nilai tinggi → fluktuasi lebar.

**Rumus (Sampel):**
$$s = \sqrt{\frac{\sum_{i=1}^{n} (x_i - \bar{x})^2}{n-1}}$$

**Contoh (CO):**
$$\sum_{i=1}^{n}(x_i - \bar{x})^2 = 0.0028790691$$
$$s_{CO} = \sqrt{\frac{0.0028790691}{275-1}} = \sqrt{\frac{0.0028790691}{274}} = 0.003242$$

### 4. Variance
**Penjelasan:** Rata-rata kuadrat selisih tiap titik data terhadap Mean; secara matematis adalah kuadrat dari Std. Deviation.

**Rumus (Sampel):**
$$s^2 = \frac{\sum_{i=1}^{n} (x_i - \bar{x})^2}{n-1}$$

**Contoh (CO):**
$$s^2_{CO} = (0.003242)^2 = 1.0508 \times 10^{-5}$$

### 5. Skewness
**Penjelasan:** Mengukur asimetri distribusi terhadap rata-rata.
* *Skewness = 0*: distribusi simetris.
* *Skewness > 0*: ekor memanjang ke kanan (nilai ekstrem tinggi) — contoh pada dataset ini: `NO2` (1.849).
* *Skewness < 0*: ekor memanjang ke kiri — contoh: `SO2` (-0.365).

**Rumus (Fisher-Pearson, sampel):**
$$Skewness = \underbrace{\frac{n}{(n-1)(n-2)}}_{A}\underbrace{\sum_{i=1}^{n}\left(\frac{x_i-\bar{x}}{s}\right)^3}_{B}$$

**Contoh (CO):**
$$A = \frac{275}{(275-1)(275-2)} = \frac{275}{74802} = 0.0036764$$
$$B = \sum_{i=1}^{n}\left(\frac{x_i-0.029244}{0.003242}\right)^3 = \left(\frac{0.025056-0.029244}{0.003242}\right)^3 + \left(\frac{0.024533-0.029244}{0.003242}\right)^3 + \ldots + \left(\frac{0.033720-0.029244}{0.003242}\right)^3 = 228.8966$$
$$Skewness_{CO} = 0.0036764 \times 228.8966 = 0.8415$$

### 6. Kurtosis
**Penjelasan:** Mengukur keruncingan/bobot ekor (*tailedness*) distribusi — seberapa ekstrem *outlier* yang ada. KNIME menghitung *excess kurtosis*.
* *Kurtosis ≈ 0*: mesokurtik (mendekati normal).
* *Kurtosis > 0*: leptokurtik, ekor tebal, banyak outlier — contoh ekstrem pada dataset ini: `NO2` (7.919).
* *Kurtosis < 0*: platikurtik, puncak lebih datar — contoh: `O3` (-0.132).

**Rumus (Excess Kurtosis, sampel):**
$$Kurtosis = \left[\underbrace{\frac{n(n+1)}{(n-1)(n-2)(n-3)}}_{A}\underbrace{\sum\left(\frac{x_i-\bar{x}}{s}\right)^4}_{B}\right] - \underbrace{\frac{3(n-1)^2}{(n-2)(n-3)}}_{C}$$

**Contoh (CO):**
$$A = \frac{275 \times 276}{(274)(273)(272)} = \frac{75900}{20346144} = 0.0037304$$
$$B = \sum_{i=1}^{n}\left(\frac{x_i-0.029244}{0.003242}\right)^4 = 1290.3911$$
$$C = \frac{3(274)^2}{(273)(272)} = \frac{225228}{74256} = 3.0331$$
$$Kurtosis_{CO} = (0.0037304 \times 1290.3911) - 3.0331 = 4.8137 - 3.0331 = 1.7806$$

### 7. Overall Sum
**Penjelasan:** Total keseluruhan nilai pada variabel yang bersangkutan.

**Rumus:**
$$Sum = \sum_{i=1}^{n} x_i$$

**Contoh (CO):**
$$Sum_{CO} = 0.025056 + 0.024533 + 0.024816 + \ldots + 0.033720 = 8.042181$$

### 8. Metrik Kualitas / Anomali Data (No. missings, No. NaNs, No. ±infs)
**Penjelasan:** Krusial saat data hasil ekstraksi API/citra satelit, karena rentan gagal rekam.
* **No. missings:** sel kosong (NULL/NA) — pada dataset ini, kolom `CO` memiliki **88** missing dari 363 baris (tersisa`n = 275`), `NO2` = 75, `SO2` = 56, `O3` = 3.
* **No. NaNs:** entri terbaca tapi tidak terdefinisi matematis (mis. 0/0).
* **No. +infs / -infs:** nilai tak terhingga.

**Perhitungan manual:** menghitung frekuensi (count) baris yang memuat nilai-nilai tersebut per kolom.

### 9. Median
**Penjelasan:** Nilai tengah data setelah diurutkan; lebih tahan (*robust*) terhadap outlier dibanding Mean.

**Rumus:**
$$n \text{ ganjil}: Median = X_{(n+1)/2} \qquad n \text{ genap}: Median = \frac{X_{n/2}+X_{(n/2)+1}}{2}$$

**Contoh (CO):** `n = 275` (ganjil), sehingga:
$$Median_{CO} = X_{(275+1)/2} = X_{138} = 0.028893$$
*(nilai pada urutan ke-138 setelah 275 data `CO` valid diurutkan menaik)*

---

## Ringkasan Alur

```
CSV (Polutan_Gresik_Terkini.csv)
   └─▶ Import ke PostgreSQL Aiven (via pgAdmin 4)
         └─▶ PostgreSQL Connector (KNIME)
               └─▶ DB Table Selector → DB Reader
                     └─▶ Statistics Node → Min, Max, Mean, Median,
                          Std. Dev, Variance, Skewness, Kurtosis,
                          Sum, Missing/NaN/Inf count, Histogram
```

Alur ini memastikan data *time-series* polutan Gresik tersimpan aman di cloud database, dapat diakses berulang, dan siap dianalisis statistiknya secara otomatis maupun diverifikasi secara manual seperti dijabarkan di atas.