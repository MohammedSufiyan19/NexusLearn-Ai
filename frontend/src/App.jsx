import { useState, useEffect } from "react"
import axios from "axios"
import Sidebar from "./components/Sidebar"
import ChatWindow from "./components/ChatWindow"
import InputBar from "./components/InputBar"

const API = "https://nexuslearn-ai-production.up.railway.app"

export default function App() {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "Hi! I'm **NexusLearn AI** by Team Nexus 🎓\n\nUpload your notes, textbooks, or question papers and ask me anything. I can also chat freely without any documents.",
      sources: [],
      route: "chat"
    }
  ])
  const [sources, setSources] = useState([])
  const [loading, setLoading] = useState(false)
  const [showSidebar, setShowSidebar] = useState(window.innerWidth >= 768)

  const fetchSources = async () => {
    try {
      const res = await axios.get(`${API}/sources`)
      setSources(res.data.sources)
    } catch (err) {
      console.error("Failed to fetch sources", err)
    }
  }

  useEffect(() => {
    fetchSources()
    const handleResize = () => setShowSidebar(window.innerWidth >= 768)
    window.addEventListener("resize", handleResize)
    return () => window.removeEventListener("resize", handleResize)
  }, [])

  const sendMessage = async (text) => {
    if (!text.trim()) return

    const userMsg = { role: "user", content: text, sources: [], route: "" }
    const updatedMessages = [...messages, userMsg]
    setMessages(updatedMessages)
    setLoading(true)

    try {
      const history = messages.map((m) => ({
        role: m.role,
        content: m.content
      }))

      const res = await axios.post(`${API}/chat`, {
        message: text,
        history: history
      })

      const aiMsg = {
        role: "assistant",
        content: res.data.answer,
        sources: res.data.sources || [],
        route: res.data.route || "chat"
      }

      setMessages([...updatedMessages, aiMsg])
    } catch {
      setMessages([
        ...updatedMessages,
        {
          role: "assistant",
          content: "Something went wrong. Please check if the backend is running.",
          sources: [],
          route: "error"
        }
      ])
    } finally {
      setLoading(false)
    }
  }

  const handleUpload = async (file) => {
    const formData = new FormData()
    formData.append("file", file)

    try {
      const res = await axios.post(`${API}/upload`, formData, {
        headers: { "Content-Type": "multipart/form-data" }
      })

      await fetchSources()

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `✅ **${res.data.filename}** uploaded successfully!\n\n${res.data.pages} pages processed into ${res.data.chunks} chunks. You can now ask questions about it.`,
          sources: [],
          route: "system"
        }
      ])
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `❌ Failed to upload file. Make sure it's a PDF, DOCX, or PPTX.`,
          sources: [],
          route: "error"
        }
      ])
    }
  }

  return (
    <div style={{
      display: "flex",
      height: "100vh",
      background: "#0f1117",
      flexDirection: "row",
      overflow: "hidden"
    }}>
      {/* sidebar — hidden on mobile */}
      {showSidebar && (
        <Sidebar sources={sources} />
      )}

      {/* main chat area */}
      <div style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        minWidth: 0,
        position: "relative"
      }}>

        {/* top bar — shows on mobile */}
        <div style={{
          padding: "10px 16px",
          borderBottom: "1px solid #1e2433",
          background: "#0d1117",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between"
        }}>
          <span style={{
            fontSize: "15px",
            fontWeight: 700,
            color: "#e2e8f0",
            letterSpacing: "-0.01em"
          }}>
            NexusLearn AI
          </span>

          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            {/* docs count badge */}
            {sources.length > 0 && (
              <span style={{
                fontSize: "11px",
                padding: "3px 8px",
                borderRadius: "99px",
                background: "#1e3a5f",
                color: "#63b3ed",
                fontWeight: 600
              }}>
                {sources.length} doc{sources.length !== 1 ? "s" : ""}
              </span>
            )}

            {/* toggle sidebar button — mobile */}
            <button
              onClick={() => setShowSidebar(!showSidebar)}
              style={{
                background: "#1a2535",
                border: "1px solid #1e2433",
                borderRadius: "8px",
                color: "#63b3ed",
                padding: "5px 10px",
                fontSize: "12px",
                cursor: "pointer"
              }}
            >
              {showSidebar ? "Hide Docs" : "Show Docs"}
            </button>
          </div>
        </div>

        <ChatWindow messages={messages} loading={loading} />
        <InputBar onSend={sendMessage} onUpload={handleUpload} loading={loading} />
      </div>
    </div>
  )
}