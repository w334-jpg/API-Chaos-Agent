import { useState, useEffect } from "react"
import { Users, UserPlus, Shield, Crown } from "lucide-react"

interface TeamMember {
    id: string
    user_email: string
    display_name: string
    role: string
    joined_at: string
}

interface Tenant {
    id: string
    name: string
    plan: string
    status: string
    quota: {
        max_team_members: number
        max_schemas: number
        distributed_workers: number
        custom_plugins: boolean
        ci_cd_integration: boolean
        sso_enabled: boolean
        advanced_analytics: boolean
    }
}

const roleIcons: Record<string, typeof Crown> = {
    owner: Crown,
    admin: Shield,
    member: Users,
    viewer: Users,
}

export default function TeamPage() {
    const [tenant, setTenant] = useState<Tenant | null>(null)
    const [members, setMembers] = useState<TeamMember[]>([])
    const [loading, setLoading] = useState(true)
    const [inviteEmail, setInviteEmail] = useState("")
    const [inviteRole, setInviteRole] = useState("member")

    useEffect(() => {
        fetchData()
    }, [])

    async function fetchData() {
        try {
            const tenantsRes = await fetch("/api/v2/tenants")
            if (tenantsRes.ok) {
                const tenants = await tenantsRes.json()
                if (tenants.length > 0) {
                    const t = tenants[0]
                    setTenant(t)
                    const membersRes = await fetch(`/api/v2/tenants/${t.id}/members`)
                    if (membersRes.ok) setMembers(await membersRes.json())
                }
            }
        } catch {
            setTenant(null)
        } finally {
            setLoading(false)
        }
    }

    async function inviteMember() {
        if (!tenant || !inviteEmail) return
        try {
            const res = await fetch(
                `/api/v2/tenants/${tenant.id}/members?email=${encodeURIComponent(inviteEmail)}&role=${inviteRole}`,
                { method: "POST" }
            )
            if (res.ok) {
                setInviteEmail("")
                fetchData()
            }
        } catch { /* ignore */ }
    }

    async function removeMember(memberId: string) {
        if (!tenant) return
        try {
            await fetch(`/api/v2/tenants/${tenant.id}/members/${memberId}`, { method: "DELETE" })
            fetchData()
        } catch { /* ignore */ }
    }

    const planLabels: Record<string, string> = {
        free: "Free",
        pro: "Professional",
        enterprise: "Enterprise",
    }

    const planColors: Record<string, string> = {
        free: "bg-gray-100 text-gray-700",
        pro: "bg-blue-100 text-blue-700",
        enterprise: "bg-purple-100 text-purple-700",
    }

    if (loading) return <p className="text-muted-foreground">Loading...</p>

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl font-bold">Team Management</h1>
                <p className="text-muted-foreground">Manage team members and tenant settings</p>
            </div>

            {tenant && (
                <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
                    <div className="rounded-lg border bg-card p-4">
                        <p className="text-sm text-muted-foreground">Organization</p>
                        <p className="mt-1 text-lg font-bold">{tenant.name}</p>
                    </div>
                    <div className="rounded-lg border bg-card p-4">
                        <p className="text-sm text-muted-foreground">Plan</p>
                        <span className={`mt-1 inline-block rounded-full px-2 py-0.5 text-xs font-medium ${planColors[tenant.plan] || ""}`}>
                            {planLabels[tenant.plan] || tenant.plan}
                        </span>
                    </div>
                    <div className="rounded-lg border bg-card p-4">
                        <p className="text-sm text-muted-foreground">Members</p>
                        <p className="mt-1 text-lg font-bold">
                            {members.length} / {tenant.quota.max_team_members}
                        </p>
                    </div>
                    <div className="rounded-lg border bg-card p-4">
                        <p className="text-sm text-muted-foreground">Features</p>
                        <div className="mt-1 flex flex-wrap gap-1">
                            {tenant.quota.custom_plugins && <span className="rounded bg-green-100 px-1.5 py-0.5 text-xs text-green-700">Plugins</span>}
                            {tenant.quota.ci_cd_integration && <span className="rounded bg-blue-100 px-1.5 py-0.5 text-xs text-blue-700">CI/CD</span>}
                            {tenant.quota.sso_enabled && <span className="rounded bg-purple-100 px-1.5 py-0.5 text-xs text-purple-700">SSO</span>}
                            {tenant.quota.advanced_analytics && <span className="rounded bg-orange-100 px-1.5 py-0.5 text-xs text-orange-700">Analytics</span>}
                        </div>
                    </div>
                </div>
            )}

            <div className="rounded-lg border bg-card p-5">
                <h2 className="mb-4 font-semibold">Team Members</h2>
                <div className="space-y-3">
                    {members.map((member) => {
                        const RoleIcon = roleIcons[member.role] || Users
                        return (
                            <div key={member.id} className="flex items-center justify-between rounded-lg border p-3">
                                <div className="flex items-center gap-3">
                                    <div className="flex h-9 w-9 items-center justify-center rounded-full bg-muted">
                                        <RoleIcon className="h-4 w-4" />
                                    </div>
                                    <div>
                                        <p className="font-medium">{member.display_name}</p>
                                        <p className="text-sm text-muted-foreground">{member.user_email}</p>
                                    </div>
                                </div>
                                <div className="flex items-center gap-3">
                                    <span className="rounded-full bg-secondary px-2.5 py-0.5 text-xs font-medium capitalize">
                                        {member.role}
                                    </span>
                                    {member.role !== "owner" && (
                                        <button
                                            onClick={() => removeMember(member.id)}
                                            className="text-xs text-red-600 hover:underline"
                                        >
                                            Remove
                                        </button>
                                    )}
                                </div>
                            </div>
                        )
                    })}
                </div>

                {tenant && members.length < tenant.quota.max_team_members && (
                    <div className="mt-4 flex items-end gap-3 border-t pt-4">
                        <div className="flex-1">
                            <label className="text-sm font-medium">Email</label>
                            <input
                                type="email"
                                value={inviteEmail}
                                onChange={(e) => setInviteEmail(e.target.value)}
                                placeholder="colleague@example.com"
                                className="mt-1 w-full rounded-lg border bg-background px-3 py-2 text-sm"
                            />
                        </div>
                        <div>
                            <label className="text-sm font-medium">Role</label>
                            <select
                                value={inviteRole}
                                onChange={(e) => setInviteRole(e.target.value)}
                                className="mt-1 rounded-lg border bg-background px-3 py-2 text-sm"
                            >
                                <option value="member">Member</option>
                                <option value="admin">Admin</option>
                                <option value="viewer">Viewer</option>
                            </select>
                        </div>
                        <button
                            onClick={inviteMember}
                            disabled={!inviteEmail}
                            className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                        >
                            <UserPlus className="h-4 w-4" />
                            Add
                        </button>
                    </div>
                )}
            </div>
        </div>
    )
}
