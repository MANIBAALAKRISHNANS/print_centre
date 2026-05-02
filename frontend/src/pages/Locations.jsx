import { useState, useContext } from "react";
import { AppData } from "../context/AppData";
function Locations() {
  const { locations, setLocations, loadAll } = useContext(AppData);
  
  const [open, setOpen] = useState(false);
  const [editName, setEditName] = useState("");

  const [newLocation, setNewLocation] = useState("");

  const saveLocation = async () => {
    const trimmedLocation = newLocation.trim();
    if (trimmedLocation === "") return;

    const url = editName
      ? `http://127.0.0.1:8000/locations/${encodeURIComponent(editName)}`
      : "http://127.0.0.1:8000/locations";

    const method = editName ? "PUT" : "POST";

    const res = await fetch(url, {
      method: method,
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ name: trimmedLocation }),
    });

    const result = await res.json();

    if (result.error) {
      alert(result.error);
      return;
    }

    if (editName) {
      setLocations((current) =>
        current.map((item) => (item === editName ? trimmedLocation : item))
      );
    } else {
      setLocations((current) =>
        current.includes(trimmedLocation) ? current : [...current, trimmedLocation]
      );
    }

    setNewLocation("");
    setEditName("");
    setOpen(false);
    loadAll();
  };

  const editLocation = (name) => {
    setEditName(name);
    setNewLocation(name);
    setOpen(true);
  };

  const deleteLocation = async (name) => {
    if (!window.confirm("Delete location?")) return;

    const res = await fetch(
      `http://127.0.0.1:8000/locations/${encodeURIComponent(name)}`,
      { method: "DELETE" }
    );

    const result = await res.json();

    if (result.error) {
      alert(result.error);
      return;
    }

    setLocations((current) => current.filter((item) => item !== name));
    loadAll();
  };

  const syncLocations = async () => {
    await loadAll();
    alert("Locations synchronized successfully");
  };

  const openAdd = () => {
    setEditName("");
    setNewLocation("");
    setOpen(true);
  };

  return (
    <div className="page">

      <h1>Shared Locations</h1>

      <p className="sub">
        Locations can be stored locally or synchronized from main system
      </p>

      <button
        className="btn"
        onClick={openAdd}
      >
        + Add Location
      </button>

      <button
        className="btn"
        style={{ marginLeft: "10px" }}
        onClick={syncLocations}
      >
        Sync Locations
      </button>

      <br /><br />

      {locations.map((item, index) => (
        <div
          className="listCard"
          key={index}
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >

          <span>{item}</span>

          <div
            style={{
              display: "flex",
              gap: "8px",
            }}
          >

            <button
              className="btn"
              onClick={() =>
                editLocation(item)
              }
            >
              Edit
            </button>

            <button
              className="btn"
              onClick={() =>
                deleteLocation(item)
              }
            >
              Delete
            </button>

          </div>

        </div>
      ))}

      {open && (
        <div className="modalOverlay">

          <div className="modalBox">

            <div className="modalHead">

              <h3>
                {editName
                  ? "Edit Location"
                  : "Add Location"}
              </h3>

              <button
                onClick={() => setOpen(false)}
              >
                ✕
              </button>

            </div>

            <form
              className="modalBody"
              onSubmit={(e) => {
                e.preventDefault();
                saveLocation();
              }}
            >

              <input
                placeholder="Location Name"
                value={newLocation}
                onChange={(e) =>
                  setNewLocation(
                    e.target.value
                  )
                }
              />

              <button
                type="submit"
                className="btn full"
              >
                {editName
                  ? "Update Location"
                  : "Save Location"}
              </button>

            </form>

          </div>

        </div>
      )}

    </div>
  );
}

export default Locations;
