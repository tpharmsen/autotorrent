interface ChatResponse { answer: string; }

const messages = document.getElementById("chat-messages");
const tokenInput = document.getElementById("chat-token") as HTMLInputElement | null;
const messageInput = document.getElementById("chat-message") as HTMLTextAreaElement | null;
const sendButton = document.getElementById("chat-send") as HTMLButtonElement | null;

if (tokenInput) tokenInput.value = localStorage.getItem("chatbot-token") ?? "";

function addMessage(role: "user" | "assistant" | "error", text: string): void {
	if (!messages) return;
	const item = document.createElement("div");
	item.className = `chat-message ${role}`;
	item.textContent = text;
	messages.appendChild(item);
	messages.scrollTop = messages.scrollHeight;
}

async function sendMessage(): Promise<void> {
	const token = tokenInput?.value.trim() ?? "";
	const message = messageInput?.value.trim() ?? "";
	if (!token || !message) {
		addMessage("error", "Enter a token and a message.");
		return;
	}
	localStorage.setItem("chatbot-token", token);
	addMessage("user", message);
	if (sendButton) sendButton.disabled = true;
	try {
		const res = await fetch("/api/chatbot", {
			method: "POST",
			headers: { "Content-Type": "application/json", "X-Chatbot-Token": token },
			body: JSON.stringify({ message }),
		});
		const raw = await res.text();
		let data: ChatResponse & { detail?: string };
		try {
			data = JSON.parse(raw) as ChatResponse & { detail?: string };
		} catch {
			throw new Error(raw || `Request failed: ${res.status}`);
		}
		if (!res.ok) throw new Error(data.detail || `Request failed: ${res.status}`);
		addMessage("assistant", data.answer);
		if (messageInput) messageInput.value = "";
	} catch (error) {
		addMessage("error", error instanceof Error ? error.message : "Chat request failed.");
	} finally {
		if (sendButton) sendButton.disabled = false;
	}
}

sendButton?.addEventListener("click", sendMessage);
messageInput?.addEventListener("keydown", (event) => {
	if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) sendMessage();
});
