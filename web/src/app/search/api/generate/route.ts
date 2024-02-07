
export const runtime = 'nodejs'
// This is required to enable streaming
export const dynamic = 'force-dynamic'

export async function POST(req: Request) {
    const input: {
        prompt: string | null
        stream: boolean
    } = await req.json()
    const url = 'http://65.108.33.93:5000/generate'

    let responseStream = new TransformStream()
    const writer = responseStream.writable.getWriter()
    const encoder = new TextEncoder()

    try {
        if (!input || !input.prompt) {
            throw new Error(`No prompt provided`)
        }
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                accept: 'text/event-stream',
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                prompt: input.prompt,
                stream: true
            })
        })

        if (!response.ok) {
            throw new Error(`Error fetching response: ${response.statusText}`)
        }

        const reader = response.body?.getReader()
        let data = ''

        if (reader) {
            const decoder = new TextDecoder()

            while (true) {
                const { done, value } = await reader.read()
                if (done) {
                    writer.close()
                    break
                }
                const chunk = decoder.decode(value)
                data += chunk

                //  Process and stream words in real-time
                const lines = data.split('\n')
                const messages = lines.filter(line => line.startsWith('data: '))

                for (const message of messages) {
                    const word = message.slice(6).trim()
                    // console.log(word)
                    writer.write(encoder.encode(word + ' '))
                }
                data = ''
            }
            reader.releaseLock()
            return new Response(responseStream.readable, {
                headers: {
                    'Content-Type': 'text/event-stream',
                    'Connection': 'keep-alive',
                    'Cache-Control': 'no-cache, no-transform'
                }
            })
        } else {
            console.error('No response body reader available')
            return new Response('failed', { status: 400 })
        }
    } catch (error) {
        console.error(error)
        return new Response('failed', { status: 500 })
    }
}
