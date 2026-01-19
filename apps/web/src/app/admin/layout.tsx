import Link from 'next/link'

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b px-6 py-4 flex items-center justify-between bg-muted/50">
        <div className="flex items-center gap-4">
            <Link href="/" className="font-bold text-lg">Vantus Admin</Link>
            <nav className="flex items-center gap-4 text-sm text-muted-foreground">
                <Link href="/admin/tenants" className="hover:text-foreground">Tenants</Link>
                <Link href="/admin/ingestion" className="hover:text-foreground">Ingestion</Link>
                <Link href="/admin/settings" className="hover:text-foreground">Settings</Link>
            </nav>
        </div>
        <div>
            <Link href="/" className="text-sm">Back to Search</Link>
        </div>
      </header>
      <main className="flex-1 container mx-auto p-6">
        {children}
      </main>
    </div>
  )
}
