import { execFile } from "node:child_process"
import { promisify } from "node:util"
import { homedir } from "node:os"
import { join } from "node:path"

const execFileAsync = promisify(execFile)
const notifier = join(homedir(), ".local", "bin", "agent-attention-notify")

export const AttentionNotifications = async () => ({
  event: async ({ event }: { event: { type: string } }) => {
    if (event.type !== "permission.asked" && event.type !== "session.idle") return

    const normalized = event.type === "permission.asked" ? "approval" : "finished"
    try {
      await execFileAsync(notifier, ["OpenCode", normalized, String(process.pid)])
    } catch {
      // Notification delivery should not interfere with the OpenCode session.
    }
  },
})
