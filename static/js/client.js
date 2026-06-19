"use strict";
function initSearch() {
    const input = document.getElementById("movie-search");
    const button = document.getElementById("search-btn");
    if (!input || !button)
        return;
    const goSearch = () => {
        const query = input.value.trim();
        if (!query)
            return;
        // matches your @app.get("/search/{query}") route
        window.location.href = `/search/${encodeURIComponent(query)}`;
    };
    button.addEventListener("click", goSearch);
    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter")
            goSearch();
    });
}
function initWipe() {
    const button = document.getElementById("wipe-btn");
    if (!button)
        return;
    button.addEventListener("click", async () => {
        const confirmed = window.confirm("This will delete ALL torrents + files + streams. Continue?");
        if (!confirmed)
            return;
        try {
            // matches your @app.delete("/admin/wipe-all")
            const res = await fetch("/admin/wipe-all?delete_files=true", {
                method: "DELETE",
            });
            if (!res.ok) {
                const errBody = await res.json().catch(() => ({}));
                throw new Error(errBody.detail || `Request failed: ${res.status}`);
            }
            const data = await res.json();
            if (data.status === "error") {
                window.alert(`Wipe failed: ${data.detail ?? "unknown error"}`);
                return;
            }
            window.alert(`Wipe complete\nTorrents removed: ${data.torrents_removed}`);
            window.location.reload();
        }
        catch (err) {
            console.error("Wipe failed:", err);
            window.alert("Wipe failed — check console for details.");
        }
    });
}
document.addEventListener("DOMContentLoaded", () => {
    initSearch();
    initWipe();
});
//# sourceMappingURL=client.js.map