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

    async function downloadChatSessionsAsCSV() {
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
                const csvData = jsonToCsv(jsonData);

                const blob = new Blob([csvData], { type: 'text/csv' });

                const a = document.createElement('a');
                const url = window.URL.createObjectURL(blob);
                a.href = url;
                a.download = 'chat_sessions.csv';
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

    function jsonToCsv(jsonData: any): string {
        let csv = 'Session ID,Session Description,User Email,Message Type,Message,Luganda Message\n';

        for (const key in jsonData) {
            const session = jsonData[key];
            const sessionId = session.session_id;
            const sessionDescription = session.session_description;
            const userEmail = session.user_email || '';

            session.messages.forEach((message: any) => {
                const messageType = message.message_type;
                const messageContent = message.message.replace(/\n/g, ' ').replace(/"/g, '""');
                const lugandaMessageContent = message.luganda_message ? message.luganda_message.replace(/\n/g, ' ').replace(/"/g, '""') : ''; // Handle cases where luganda_message is null or undefined
                csv += `${sessionId},"${sessionDescription}","${userEmail}","${messageType}","${messageContent}","${lugandaMessageContent}"\n`;
            });
        }

        return csv;
    }


    return (
        <div className="mx-auto container">
            <AdminPageTitle title="Download Chat Sessions" icon={<ConnectorIcon size={32} />} />
            <div className='flex flex-row w-full gap-[2rem]'>
                <button
                    className={`bg-blue-500 p-3 text-white rounded ${loading ? 'opacity-50 cursor-not-allowed' : ''}`}
                    onClick={() => downloadChatSessions()}
                    disabled={loading}
                >
                    {loading ? 'Downloading...' : 'Download Current Chat Json'}
                </button>
                <button
                    className={`bg-blue-500 p-3 text-white rounded ${loading ? 'opacity-50 cursor-not-allowed' : ''}`}
                    onClick={() => downloadChatSessionsAsCSV()}
                    disabled={loading}
                >
                    {loading ? 'Downloading...' : 'Download Current Chat csv'}
                </button>
            </div>
            {error && <p className="text-red-500 mt-2">{error}</p>}
        </div>
    );
};

export default SessionsDownloadPage;
