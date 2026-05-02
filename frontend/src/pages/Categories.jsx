import { useState, useContext } from "react";
import { AppData } from "../context/AppData";

function Categories() {
  const { categories, setCategories, loadAll } = useContext(AppData);

  const [open, setOpen] = useState(false);
  const [editName, setEditName] = useState("");

  const [newCategory, setNewCategory] = useState("");




  const saveCategory = async () => {
    const trimmedCategory = newCategory.trim();
    if (trimmedCategory === "") return;

    const url = editName
      ? `http://127.0.0.1:8000/categories/${encodeURIComponent(editName)}`
      : "http://127.0.0.1:8000/categories";

    const method = editName ? "PUT" : "POST";

    const res = await fetch(url, {
      method: method,
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        name: trimmedCategory,
      }),
    });

    const result = await res.json();

    if (result.error) {
      alert(result.error);
      return;
    }

    if (editName) {
      setCategories((current) =>
        current.map((item) => (item === editName ? trimmedCategory : item))
      );
    } else {
      setCategories((current) =>
        current.includes(trimmedCategory) ? current : [...current, trimmedCategory]
      );
    }

    setNewCategory("");
    setEditName("");
    setOpen(false);
    loadAll();
  };

  const editCategory = (name) => {
    setEditName(name);
    setNewCategory(name);
    setOpen(true);
  };

  const deleteCategory = async (name) => {
    if (!window.confirm("Delete category?")) return;

    const res = await fetch(
      `http://127.0.0.1:8000/categories/${encodeURIComponent(name)}`,
      {
        method: "DELETE",
      }
    );

    const result = await res.json();

    if (result.error) {
      alert(result.error);
      return;
    }

    setCategories((current) => current.filter((item) => item !== name));
    loadAll();
  };

  const openAdd = () => {
    setEditName("");
    setNewCategory("");
    setOpen(true);
  };

  return (
    <div className="page">

      <h1>Printer Categories</h1>

      <p className="sub">
        Manage print categories used in Print Center
      </p>

      <button
        className="btn"
        onClick={openAdd}
      >
        + Add Category
      </button>

      <br /><br />

      {categories.map((item, index) => (
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
                editCategory(item)
              }
            >
              Edit
            </button>

            <button
              className="btn"
              onClick={() =>
                deleteCategory(item)
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
                  ? "Edit Category"
                  : "Add Category"}
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
                saveCategory();
              }}
            >

              <input
                placeholder="Category Name"
                value={newCategory}
                onChange={(e) =>
                  setNewCategory(
                    e.target.value
                  )
                }
              />

              <button
                type="submit"
                className="btn full"
              >
                {editName
                  ? "Update Category"
                  : "Save Category"}
              </button>

            </form>

          </div>

        </div>
      )}

    </div>
  );
}

export default Categories;
