import { useState, useEffect } from "react"
import { Network, Plus, Trash2, Heart, Activity } from "lucide-react"

interface Worker {
    id: string
    name: string
    status: string
    capabilities: { max_concurrency: number; region: string }
    completed_tasks: number
    failed_tasks: number
    last_heartbeat: number
}

export default function DistributedPage() {
    const [workers, setWorkers] = useState<Worker[]>([])
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        fetchWorkers()
        const interval = setInterval(fetchWorkers, 5000)
        return () => clearInterval(interval)
    }, [])

    async function fetchWorkers() {
        try {
            const res = await fetch("/api/v2/distributed/workers")
            if (res.ok) {
                const data = await res.json()
                setWorkers(data)
            }
        } catch {
            setWorkers([])
        } finally {
            setLoading(false)
        }
    }

    async function registerWorker() {
        try {
            const res = await fetch("/api/v2/distributed/workers/register?name=worker-new&max_concurrency=100&region=default", {
                method: "POST",
            })
            if (res.ok) fetchWorkers()
        } catch { /* ignore */ }
    }

    async function deregisterWorker(id: string) {
        try {
            const res = await fetch(`/api/v2/distributed/workers/${id}`, { method: "DELETE" })
            if (res.ok) fetchWorkers()
        } catch { /* ignore */ }
    }

    async function heartbeat(id: string) {
        try {
            await fetch(`/api/v2/distributed/workers/${id}/heartbeat`, { method: "POST" })
            fetchWorkers()
        } catch { /* ignore */ }
    }

    const statusColor: Record<string, string> = {
        idle: "bg-green-500",
        running: "bg-blue-500",
        offline: "bg-gray-400",
        draining: "bg-yellow-500",
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold">Distributed Workers</h1>
                    <p className="text-muted-foreground">Manage distributed chaos test workers</p>
                </div>
                <button
                    onClick={registerWorker}
                    className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
                >
                    <Plus className="h-4 w-4" />
                    Register Worker
                </button>
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                <div className="rounded-lg border bg-card p-4">
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Network className="h-4 w-4" />
                        Total Workers
                    </div>
                    <p className="mt-1 text-2xl font-bold">{workers.length}</p>
                </div>
                <div className="rounded-lg border bg-card p-4">
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Activity className="h-4 w-4" />
                        Active Workers
                    </div>
                    <p className="mt-1 text-2xl font-bold">
                        {workers.filter((w) => w.status !== "offline").length}
                    </p>
                </div>
                <div className="rounded-lg border bg-card p-4">
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Heart className="h-4 w-4" />
                        Total Tasks Completed
                    </div>
                    <p className="mt-1 text-2xl font-bold">
                        {workers.reduce((acc, w) => acc + w.completed_tasks, 0)}
                    </p>
                </div>
            </div>

            {loading ? (
                <p className="text-muted-foreground">Loading workers...</p>
            ) : workers.length === 0 ? (
                <div className="rounded-lg border border-dashed p-12 text-center">
                    <Network className="mx-auto h-12 w-12 text-muted-foreground" />
                    <p className="mt-4 text-lg font-medium">No workers registered</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                        Register a worker to start distributed chaos testing
                    </p>
                </div>
            ) : (
                <div className="space-y-3">
                    {workers.map((worker) => (
                        <div
                            key={worker.id}
                            className="flex items-center justify-between rounded-lg border bg-card p-4"
                        >
                            <div className="flex items-center gap-4">
                                <div className={`h-3 w-3 rounded-full ${statusColor[worker.status] || "bg-gray-400"}`} />
                                <div>
                                    <p className="font-medium">{worker.name}</p>
                                    <p className="text-sm text-muted-foreground">
                                        Region: {worker.capabilities.region} · Concurrency: {worker.capabilities.max_concurrency}
                                    </p>
                                </div>
                            </div>
                            <div className="flex items-center gap-4">
                                <div className="text-right text-sm">
                                    <p className="text-green-600">{worker.completed_tasks} completed</p>
                                    <p className="text-red-600">{worker.failed_tasks} failed</p>
                                </div>
                                <button
                                    onClick={() => heartbeat(worker.id)}
                                    className="rounded p-1.5 text-muted-foreground hover:bg-accent"
                                    title="Send heartbeat"
                                >
                                    <Heart className="h-4 w-4" />
                                </button>
                                <button
                                    onClick={() => deregisterWorker(worker.id)}
                                    className="rounded p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                                    title="Deregister worker"
                                >
                                    <Trash2 className="h-4 w-4" />
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}
