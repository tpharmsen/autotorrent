const form = document.getElementById("login-form") as HTMLFormElement | null;
const password = document.getElementById("login-password") as HTMLInputElement | null;
const error = document.getElementById("login-error");
const submit = document.getElementById("login-submit") as HTMLButtonElement | null;

form?.addEventListener("submit", async (event) => {
	event.preventDefault();
	if (!password?.value || submit?.disabled) return;
	if (submit) submit.disabled = true;
	if (error) error.textContent = "";
	try {
		const response = await fetch("/api/auth/login", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ password: password.value }),
		});
		const data = (await response.json()) as { detail?: string; redirect?: string };
		if (!response.ok) throw new Error(data.detail || "Login failed.");
		window.location.href = data.redirect || "/select";
	} catch (reason) {
		if (error) error.textContent = reason instanceof Error ? reason.message : "Login failed.";
	} finally {
		if (submit) submit.disabled = false;
		password?.select();
	}
});
