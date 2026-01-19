import { NextRequest, NextResponse } from 'next/server';

export const runtime = 'edge';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { query } = body;

    if (!query) {
      return NextResponse.json({ error: 'Missing query' }, { status: 400 });
    }

    const backendUrl = process.env.RAG_API_URL || 'http://localhost:8000';
    const apiKey = process.env.RAG_API_KEY || '';

    const res = await fetch(`${backendUrl}/query_stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`
      },
      body: JSON.stringify({ query, k: 5, stream: true })
    });

    if (!res.ok) {
        const text = await res.text();
        return NextResponse.json({ error: `Backend error: ${text}` }, { status: res.status });
    }

    // Pass through the stream
    return new Response(res.body, {
      headers: {
        'Content-Type': 'application/x-ndjson',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive'
      }
    });

  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
