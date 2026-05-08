import { useState, useContext } from "react";
import { AppData } from "../context/AppData";
import { useFetch } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { SkeletonLine } from "../components/Skeleton";
import EmptyState from "../components/EmptyState";
import { API_BASE_URL } from "../config";

function Categories() {
  const { categories, setCategories, loadAll } = useContext(AppData);

  const [open, setOpen] = useState(false);
  const [editName, setEditName] = useState("");

  const [newCategory, setNewCategory] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(null); // stores name of cat to delete
  const [loading, setLoading] = useState(true);
  const authFetch = useFetch();
  const toast = useToast();




  const saveCategory = async () => {
    const trimmedCategory = newCategory.trim();
    if (trimmedCategory === "") return;

    // Fixed: replaced hardcoded URL
    const url = editName
      ? `${API_BASE_URL}/categories/${encodeURIComponent(editName)}`
      : `${API_BASE_URL}/categories`;

    const method = editName ? "PUT" : "POST";

    const res = await authFetch(url, {
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
      toast.error(result.error);
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
    toast.success(`Category ${editName ? "updated" : "saved"} successfully`);
  };

  const editCategory = (name) => {
    setEditName(name);
    setNewCategory(name);
    setOpen(true);
  };

  const deleteCategory = async (name) => {
    try {
      const res = await authFetch(
        `${API_BASE_URL}/categories/${encodeURIComponent(name)}`,
        {
          method: "DELETE",
        }
      );

      const result = await res.json();

      if (result.error) {
        toast.error(result.error);
        return;
      }

      setCategories((current) => current.filter((item) => item !== name));
      loadAll();
      toast.success("Category deleted");
      setConfirmDelete(null);
    } catch (err) {
      toast.error("Failed to delete category");
    }
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

      {categories.length === 0 ? (
        <EmptyState
            icon="📂"
            title="No categories yet"
            subtitle="Categories are used to route print jobs to the right printer type."
            action={openAdd}
            actionLabel="Add First Category"
        />
      ) : categories.map((item, index) => (
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
                setConfirmDelete(item)
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

      {confirmDelete && (
        <div className="modalOverlay">
          <div className="modalBox" style={{ textAlign: "center", padding: "30px" }}>
             <h3 style={{ marginBottom: "15px" }}>Delete Category?</h3>
             <p style={{ color: "#666", marginBottom: "25px" }}>
               Are you sure you want to delete <strong>{confirmDelete}</strong>? This action cannot be undone.
             </p>
             <div style={{ display: "flex", gap: "10px", justifyContent: "center" }}>
               <button 
                  className="btn" 
                  style={{ background: "#ef4444" }}
                  onClick={() => deleteCategory(confirmDelete)}
                >Delete</button>
               <button 
                  className="btn" 
                  style={{ background: "#6b7280" }}
                  onClick={() => setConfirmDelete(null)}
                >Cancel</button>
             </div>
          </div>
        </div>
      )}

    </div>
  );
}

export default Categories;
