import React, { useState } from 'react';

export default function CheckinApp() {
  const [checkins, setCheckins] = useState([]);
  const [showMenu, setShowMenu] = useState(false);
  const [checkInTime, setCheckInTime] = useState(null);

  const handleCheckIn = () => {
    const now = new Date();
    const timeString = now.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    });
    const dateString = now.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });

    setCheckins([...checkins, { time: timeString, date: dateString }]);
    setCheckInTime(`${timeString} on ${dateString}`);

    // Show confirmation message
    setTimeout(() => setCheckInTime(null), 3000);
  };

  return (
    <div className="app-container">
      <style>{`
        * {
          margin: 0;
          padding: 0;
          box-sizing: border-box;
        }

        body, html {
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
          background: #f5f5f5;
        }

        .app-container {
          min-height: 100vh;
          background: #f5f5f5;
          display: flex;
          flex-direction: column;
          padding: 20px;
          max-width: 600px;
          margin: 0 auto;
          font-family: 'Courier New', monospace;
        }

        .header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 30px;
          position: relative;
        }

        .frame-label {
          color: #999;
          font-size: 12px;
          font-weight: 400;
          letter-spacing: 0.5px;
        }

        .menu-button {
          width: 50px;
          height: 50px;
          border-radius: 25px;
          background: #558B4D;
          border: none;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 24px;
          color: white;
          transition: all 0.3s ease;
          box-shadow: 0 4px 12px rgba(85, 139, 77, 0.3);
        }

        .menu-button:active {
          transform: scale(0.95);
          box-shadow: 0 2px 6px rgba(85, 139, 77, 0.2);
        }

        .menu-button:hover {
          background: #4a7642;
        }

        .menu-dropdown {
          position: absolute;
          top: 60px;
          right: 0;
          background: white;
          border-radius: 12px;
          box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
          overflow: hidden;
          z-index: 100;
          min-width: 150px;
        }

        .menu-item {
          padding: 12px 16px;
          cursor: pointer;
          border: none;
          background: none;
          width: 100%;
          text-align: left;
          font-size: 14px;
          color: #333;
          transition: background 0.2s;
        }

        .menu-item:hover {
          background: #f0f0f0;
        }

        .title {
          font-size: 32px;
          color: #000;
          font-weight: 400;
          letter-spacing: -0.5px;
          margin-bottom: 40px;
          margin-top: 20px;
        }

        .main-container {
          flex: 1;
          background: #9DB89D;
          border-radius: 30px;
          padding: 30px;
          display: flex;
          flex-direction: column;
          justify-content: flex-start;
          align-items: center;
          box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
          min-height: 400px;
        }

        .loading-bar {
          width: 100%;
          height: 6px;
          background: rgba(85, 139, 77, 0.4);
          border-radius: 3px;
          margin-bottom: 40px;
          overflow: hidden;
        }

        .loading-bar-fill {
          height: 100%;
          background: #558B4D;
          width: 40%;
          animation: loading 2s ease-in-out infinite;
        }

        @keyframes loading {
          0%, 100% { width: 40%; }
          50% { width: 80%; }
        }

        .checkin-content {
          width: 100%;
          display: flex;
          flex-direction: column;
          align-items: center;
        }

        .checkin-status {
          font-size: 16px;
          color: rgba(0, 0, 0, 0.6);
          margin-bottom: 20px;
          text-align: center;
        }

        .checkin-button {
          background: #558B4D;
          color: white;
          border: none;
          padding: 14px 36px;
          border-radius: 25px;
          font-size: 16px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.3s ease;
          margin-bottom: 30px;
          box-shadow: 0 4px 12px rgba(85, 139, 77, 0.3);
        }

        .checkin-button:active {
          transform: scale(0.95);
        }

        .checkin-button:hover {
          background: #4a7642;
        }

        .confirmation-message {
          background: rgba(255, 255, 255, 0.9);
          color: #558B4D;
          padding: 16px 20px;
          border-radius: 12px;
          margin-bottom: 20px;
          text-align: center;
          font-size: 14px;
          animation: slideDown 0.3s ease;
        }

        @keyframes slideDown {
          from {
            opacity: 0;
            transform: translateY(-10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        .checkins-list {
          width: 100%;
          margin-top: 20px;
        }

        .checkin-item {
          background: rgba(255, 255, 255, 0.2);
          padding: 12px 16px;
          border-radius: 10px;
          margin-bottom: 10px;
          font-size: 13px;
          color: rgba(0, 0, 0, 0.7);
        }

        .checkin-time {
          font-weight: 600;
          color: #333;
        }

        @media (max-width: 480px) {
          .app-container {
            padding: 16px;
          }

          .title {
            font-size: 28px;
            margin-bottom: 30px;
          }

          .main-container {
            border-radius: 25px;
            padding: 24px;
            min-height: 350px;
          }

          .checkin-button {
            padding: 12px 30px;
            font-size: 15px;
          }
        }
      `}</style>

      <div className="header">
        <div className="frame-label">Frame 1</div>
        <button
          className="menu-button"
          onClick={() => setShowMenu(!showMenu)}
        >
          ≡
        </button>
        {showMenu && (
          <div className="menu-dropdown">
            <button
              className="menu-item"
              onClick={() => {
                setCheckins([]);
                setShowMenu(false);
              }}
            >
              Clear History
            </button>
            <button
              className="menu-item"
              onClick={() => setShowMenu(false)}
            >
              Settings
            </button>
          </div>
        )}
      </div>

      <h1 className="title">Check-in today</h1>

      <div className="main-container">
        <div className="loading-bar">
          <div className="loading-bar-fill"></div>
        </div>

        <div className="checkin-content">
          {checkInTime && (
            <div className="confirmation-message">
              ✓ Checked in at {checkInTime}
            </div>
          )}

          <p className="checkin-status">
            {checkins.length === 0
              ? "You haven't checked in yet today"
              : `${checkins.length} check-in${checkins.length !== 1 ? 's' : ''} today`}
          </p>

          <button
            className="checkin-button"
            onClick={handleCheckIn}
          >
            Check In Now
          </button>

          {checkins.length > 0 && (
            <div className="checkins-list">
              {checkins.map((checkin, index) => (
                <div key={index} className="checkin-item">
                  <span className="checkin-time">{checkin.time}</span>
                  <span> • {checkin.date}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
