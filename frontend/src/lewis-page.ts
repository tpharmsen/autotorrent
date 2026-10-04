interface AgentMessage {
	role: "user" | "assistant";
	content: string;
}

interface AgentResponse {
	answer?: string;
	detail?: string;
}

const messagesElement = document.getElementById("agent-messages");
const input = document.getElementById("agent-input") as HTMLTextAreaElement | null;
const sendButton = document.getElementById("agent-send") as HTMLButtonElement | null;
const clearButton = document.getElementById("agent-clear") as HTMLButtonElement | null;
const logoutButton = document.getElementById("agent-logout") as HTMLButtonElement | null;
const approval = document.getElementById("agent-approve") as HTMLInputElement | null;
const conversation: AgentMessage[] = [];
let requestInFlight = false;

function addMessage(role: "user" | "assistant" | "error", content: string): void {
	if (!messagesElement) return;
	const message = document.createElement("div");
	message.className = `agent-message ${role}`;
	message.textContent = content;
	messagesElement.appendChild(message);
	messagesElement.scrollTop = messagesElement.scrollHeight;
}

async function sendMessage(): Promise<void> {
	const content = input?.value.trim() ?? "";
	if (!content || requestInFlight) return;

	requestInFlight = true;
	if (sendButton) sendButton.disabled = true;
	conversation.push({ role: "user", content });
	addMessage("user", content);
	if (input) input.value = "";

	try {
		const response = await fetch("/api/agent", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({
				messages: conversation,
				approve_commands: approval?.checked ?? false,
			}),
		});
		const data = (await response.json()) as AgentResponse;
		if (!response.ok) throw new Error(data.detail || `Request failed: ${response.status}`);
		const answer = data.answer || "Lewis did not return a response.";
		conversation.push({ role: "assistant", content: answer });
		addMessage("assistant", answer);
	} catch (error) {
		conversation.pop();
		addMessage("error", error instanceof Error ? error.message : "Agent request failed.");
	} finally {
		requestInFlight = false;
		if (sendButton) sendButton.disabled = false;
		input?.focus();
	}
}

function clearConversation(): void {
	conversation.length = 0;
	if (messagesElement) {
		messagesElement.replaceChildren();
		addMessage("assistant", "New conversation started. What should we work on?");
	}
	input?.focus();
}

sendButton?.addEventListener("click", sendMessage);
clearButton?.addEventListener("click", clearConversation);
logoutButton?.addEventListener("click", async () => {
	await fetch("/api/auth/logout", { method: "POST" });
	window.location.href = "/login";
});
input?.addEventListener("keydown", (event) => {
	if (event.key === "Enter" && !event.shiftKey) {
		event.preventDefault();
		sendMessage();
	}
});
