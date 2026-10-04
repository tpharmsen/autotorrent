const launcherLogoutButton = document.getElementById("launcher-logout") as HTMLButtonElement | null;

launcherLogoutButton?.addEventListener("click", async () => {
	await fetch("/api/auth/logout", { method: "POST" });
	window.location.href = "/login";
});
