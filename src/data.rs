use pyo3::types::PyBytes;
use pyo3::{exceptions::PyValueError, prelude::*};
use symbolica_data::{Asset, Data};

mod data_assets {
    include!("data_assets.rs");
}

fn assets() -> &'static [Asset] {
    data_assets::ALL
}

#[pyfunction]
pub(crate) fn _set_data_directories(directories: Vec<String>) {
    Data::set_directories(directories.into_iter().map(Into::into).collect());
}

#[pyfunction]
pub(crate) fn _data_manifest() -> String {
    let records: Vec<_> = assets()
        .iter()
        .map(|asset| {
            let loaded = asset.is_loaded();
            let mut record = serde_json::to_value(asset).unwrap();
            record["loaded"] = loaded.into();
            record
        })
        .collect();
    serde_json::json!({"schema": 1, "bundle": "data", "assets": records}).to_string()
}

#[pyfunction]
pub(crate) fn _install_data_asset(name: &str, payload: &[u8]) -> PyResult<()> {
    let asset = assets()
        .iter()
        .find(|asset| asset.name == name)
        .ok_or_else(|| PyValueError::new_err(format!("unknown data asset: {name}")))?;
    asset
        .install(payload.to_vec())
        .map_err(|error| PyValueError::new_err(error.to_string()))
}

#[pyfunction]
pub(crate) fn _read_data_asset<'py>(py: Python<'py>, name: &str) -> PyResult<Bound<'py, PyBytes>> {
    let asset = assets()
        .iter()
        .find(|asset| asset.name == name)
        .ok_or_else(|| PyValueError::new_err(format!("unknown data asset: {name}")))?;
    let bytes = asset
        .bytes()
        .map_err(|error| PyValueError::new_err(error.to_string()))?;
    Ok(PyBytes::new(py, &bytes))
}
