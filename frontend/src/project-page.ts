import { escapeHtml } from "./render.js";

interface ChatResponse {
	answer: string;
	figure?: { filename: string; modified: number } | null;
}
const messages = document.getElementById("chat-messages");
const tokenInput = document.getElementById("chat-token") as HTMLInputElement | null;
const messageInput = document.getElementById("chat-message") as HTMLTextAreaElement | null;
const sendButton = document.getElementById("chat-send") as HTMLButtonElement | null;
const resetButton = document.getElementById("chat-reset") as HTMLButtonElement | null;
const figure = document.getElementById("project-figure");
const figureStatus = document.getElementById("project-figures-status");
let requestInFlight = false;

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
	if (requestInFlight) return;
	requestInFlight = true;
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
		if (data.figure && figure) {
			const name = escapeHtml(data.figure.filename);
			const url = `/project-figures/${encodeURIComponent(data.figure.filename)}?v=${data.figure.modified}`;
			figure.innerHTML = `<figure><img src="${url}" alt="${name}"><figcaption>${name}</figcaption></figure>`;
			if (figureStatus) figureStatus.textContent = "Showing the figure requested in the conversation.";
		}
		if (messageInput) messageInput.value = "";
	} catch (error) {
		addMessage("error", error instanceof Error ? error.message : "Chat request failed.");
	} finally {
		requestInFlight = false;
		if (sendButton) sendButton.disabled = false;
	}
}

async function resetAgent(): Promise<void> {
	const token = tokenInput?.value.trim() ?? "";
	if (!token) {
		addMessage("error", "Enter a token before resetting the agent.");
		return;
	}
	if (resetButton) resetButton.disabled = true;
	try {
		const res = await fetch("/api/chatbot/reset", {
			method: "POST",
			headers: { "X-Chatbot-Token": token },
		});
		const raw = await res.text();
		let data: { answer?: string; detail?: string };
		try {
			data = JSON.parse(raw) as { answer?: string; detail?: string };
		} catch {
			throw new Error(raw || `Request failed: ${res.status}`);
		}
		if (!res.ok) throw new Error(data.detail || `Request failed: ${res.status}`);
		if (messages) messages.replaceChildren();
		if (messageInput) messageInput.value = "";
		if (figure) figure.replaceChildren();
		if (figureStatus) figureStatus.textContent = "Ask the assistant to show a training or validation figure.";
		addMessage("assistant", data.answer || "Agent reset.");
	} catch (error) {
		addMessage("error", error instanceof Error ? error.message : "Agent reset failed.");
	} finally {
		if (resetButton) resetButton.disabled = false;
	}
}

sendButton?.addEventListener("click", sendMessage);
resetButton?.addEventListener("click", resetAgent);
messageInput?.addEventListener("keydown", (event) => {
	if (event.key === "Enter" && !event.shiftKey) {
		event.preventDefault();
		sendMessage();
	}
});
