import { useState, useEffect } from "react"
import { Puzzle, Power, PowerOff, Play } from "lucide-react"

interface FaultPlugin {
    id: string
    manifest: {
        name: string
        version: string
        description: string
        scenario_type: string
        author: string
        tags: string[]
    }
    status: string
    execution_count: number
}

export default function PluginsPage() {
    const [plugins, setPlugins] = useState<FaultPlugin[]>([])
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        fetchPlugins()
    }, [])

    async function fetchPlugins() {
        try {
            const res = await fetch("/api/v2/plugins")
            if (res.ok) {
                const data = await res.json()
                setPlugins(data)
            }
        } catch {
            setPlugins([])
        } finally {
            setLoading(false)
        }
    }

    async function togglePlugin(name: string, enable: boolean) {
        try {
            const action = enable ? "enable" : "disable"
            const res = await fetch(`/api/v2/plugins/${name}/${action}`, { method: "POST" })
            if (res.ok) fetchPlugins()
        } catch { /* ignore */ }
    }

    const statusColor: Record<string, string> = {
        enabled: "bg-green-500",
        disabled: "bg-gray-400",
        error: "bg-red-500",
    }

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl font-bold">Fault Plugins</h1>
                <p className="text-muted-foreground">Manage and execute custom fault injection plugins</p>
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                <div className="rounded-lg border bg-card p-4">
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Puzzle className="h-4 w-4" />
                        Total Plugins
                    </div>
                    <p className="mt-1 text-2xl font-bold">{plugins.length}</p>
                </div>
                <div className="rounded-lg border bg-card p-4">
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Power className="h-4 w-4" />
                        Enabled
                    </div>
                    <p className="mt-1 text-2xl font-bold">
                        {plugins.filter((p) => p.status === "enabled").length}
                    </p>
                </div>
                <div className="rounded-lg border bg-card p-4">
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Play className="h-4 w-4" />
                        Total Executions
                    </div>
                    <p className="mt-1 text-2xl font-bold">
                        {plugins.reduce((acc, p) => acc + p.execution_count, 0)}
                    </p>
                </div>
            </div>

            {loading ? (
                <p className="text-muted-foreground">Loading plugins...</p>
            ) : (
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    {plugins.map((plugin) => (
                        <div key={plugin.id} className="rounded-lg border bg-card p-5">
                            <div className="flex items-start justify-between">
                                <div className="flex items-center gap-3">
                                    <div className={`h-3 w-3 rounded-full ${statusColor[plugin.status] || "bg-gray-400"}`} />
                                    <div>
                                        <h3 className="font-semibold">{plugin.manifest.name}</h3>
                                        <p className="text-sm text-muted-foreground">v{plugin.manifest.version}</p>
                                    </div>
                                </div>
                                <div className="flex gap-2">
                                    {plugin.status === "enabled" ? (
                                        <button
                                            onClick={() => togglePlugin(plugin.manifest.name, false)}
                                            className="rounded p-1.5 text-muted-foreground hover:bg-accent"
                                            title="Disable plugin"
                                        >
                                            <PowerOff className="h-4 w-4" />
                                        </button>
                                    ) : (
                                        <button
                                            onClick={() => togglePlugin(plugin.manifest.name, true)}
                                            className="rounded p-1.5 text-muted-foreground hover:bg-accent"
                                            title="Enable plugin"
                                        >
                                            <Power className="h-4 w-4" />
                                        </button>
                                    )}
                                </div>
                            </div>
                            <p className="mt-3 text-sm text-muted-foreground">{plugin.manifest.description}</p>
                            <div className="mt-3 flex items-center gap-4 text-xs text-muted-foreground">
                                <span>Type: {plugin.manifest.scenario_type}</span>
                                <span>Author: {plugin.manifest.author}</span>
                                <span>Executions: {plugin.execution_count}</span>
                            </div>
                            {plugin.manifest.tags.length > 0 && (
                                <div className="mt-2 flex flex-wrap gap-1">
                                    {plugin.manifest.tags.map((tag) => (
                                        <span key={tag} className="rounded-full bg-secondary px-2 py-0.5 text-xs">
                                            {tag}
                                        </span>
                                    ))}
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}
