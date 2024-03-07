"use client";

import { useState } from 'react';
import { AdminPageTitle } from "@/components/admin/Title";
import { ConnectorIcon } from "@/components/icons/icons";

const SessionsDownloadPage = () => {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    async function downloadChatSessions() {
        try {
            setLoading(true);
            const response = await fetch("/api/chat/user-chats", {
                method: "GET",
                headers: {
                    "Content-Type": "application/json",
                },
            });

            if (response.ok) {
                const jsonData = await response.json();
                const formattedJson = JSON.stringify(jsonData, null, 4);

                const blob = new Blob([formattedJson], { type: 'application/json' });

                const a = document.createElement('a');
                const url = window.URL.createObjectURL(blob);
                a.href = url;
                a.download = 'chat_sessions.json';
                document.body.appendChild(a);

                // Trigger the download
                a.click();

                // Remove the link and revoke the URL
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
            } else {
                console.error(`Error: ${response.status} - ${response.statusText}`);
                setError(`Error: ${response.status} - ${response.statusText}`);
            }
        } catch (error) {
            console.error("An error occurred:", error);
            setError("An error occurred. Please try again.");
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className="mx-auto container">
            <AdminPageTitle title="Download Chat Sessions" icon={<ConnectorIcon size={32} />} />
            <button
                className={`bg-blue-500 p-3 text-white rounded ${loading ? 'opacity-50 cursor-not-allowed' : ''}`}
                onClick={() => downloadChatSessions()}
                disabled={loading}
            >
                {loading ? 'Downloading...' : 'Download Current Chat Sessions'}
            </button>
            {error && <p className="text-red-500 mt-2">{error}</p>}
        </div>
    );
};

export default SessionsDownloadPage;
