import React from 'react';

export function SkeletonLine({ width = "100%", height = "16px", style = {} }) {
    return (
        <div className="skeleton-shimmer" style={{
            width, height,
            background: "linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%)",
            backgroundSize: "200% 100%",
            borderRadius: "4px",
            ...style
        }} />
    );
}

export function SkeletonTableRow({ cols = 6 }) {
    return (
        <tr>
            {Array(cols).fill(0).map((_, i) => (
                <td key={i}>
                    <SkeletonLine width={i === 0 ? "60px" : i === cols - 1 ? "80px" : "100%"} />
                </td>
            ))}
        </tr>
    );
}

export function SkeletonTable({ rows = 5, cols = 6 }) {
    return (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
            <table style={{ width: "100%" }}>
                <tbody>
                    {Array(rows).fill(0).map((_, i) => <SkeletonTableRow key={i} cols={cols} />)}
                </tbody>
            </table>
        </div>
    );
}
