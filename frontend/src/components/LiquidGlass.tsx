import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { getDisplacementFilter } from "../utils/liquidGlass";

interface LiquidGlassProps {
    children: ReactNode;
    className?: string;
    depth?: number;
    strength?: number;
    chromaticAberration?: number;
    blur?: number;
    color?: "black" | "white" | "transparent";
    background?: string;
    freeze?: boolean;
    button?: boolean;
}

const supportsBackdropFilterUrl = (() => {
    if (typeof document === "undefined") return false;
    const testEl = document.createElement("div");
    testEl.style.cssText = "backdrop-filter: url(#test)";
    return (
        testEl.style.backdropFilter === "url(#test)" ||
        testEl.style.backdropFilter === 'url("#test")'
    );
})();

export function LiquidGlass({
    children,
    className = "",
    depth = 10,
    strength = 100,
    chromaticAberration = 2,
    blur = 0,
    color = "transparent",
    background,
    freeze = false,
    button = false,
}: LiquidGlassProps) {
    const wrapperRef = useRef<HTMLDivElement>(null);
    const glassRef = useRef<HTMLDivElement>(null);
    const contentRef = useRef<HTMLDivElement>(null);
    const spinnerRef = useRef<HTMLDivElement>(null);
    const [isHovering, setIsHovering] = useState(false);

    const colorClasses: Record<string, React.CSSProperties> = {
        black: {
            background: "#09090b80",
            boxShadow: "inset 0 0 4px 0px #fafafa80",
            filter: "brightness(0.6)",
        },
        white: {
            background: "#fafafa80",
            boxShadow: "inset 0 0 4px 0px #fafafa80",
        },
        transparent: {
            background: "#09090b00",
            boxShadow: "inset 0 0 4px 0px #fafafa80",
        },
    };

    const redraw = useCallback(() => {
        const content = contentRef.current;
        const glass = glassRef.current;
        const bgImg = spinnerRef.current?.querySelector("img");
        if (!content || !glass) return;

        const rect = content.getBoundingClientRect();
        const width = Math.round(rect.width);
        const height = Math.round(rect.height);
        const radius = parseFloat(
            getComputedStyle(wrapperRef.current!).borderRadius || "0"
        );

        const saturate = button ? 1.2 : 1.5;
        const brightness = button ? 1.6 : 1.1;

        glass.style.height = `${height}px`;
        glass.style.width = `${width}px`;

        if (bgImg) {
            bgImg.style.width = `${width}px`;
            bgImg.style.height = `${width}px`;
        }

        if (supportsBackdropFilterUrl) {
            glass.style.backdropFilter = `blur(${blur / 2}px) url('${getDisplacementFilter({
                height,
                width,
                radius,
                depth,
                strength,
                chromaticAberration,
            })}') blur(${blur}px) brightness(${brightness}) saturate(${saturate})`;
        } else {
            (glass.style as any).WebkitBackdropFilter = `blur(${width / 10}px) saturate(180%)`;
            (glass.style as any).backdropFilter = `blur(${width / 10}px) saturate(180%)`;
        }
    }, [blur, chromaticAberration, depth, strength, button]);

    useEffect(() => {
        if (!wrapperRef.current) return;
        redraw();
        const observer = new ResizeObserver(() => redraw());
        observer.observe(wrapperRef.current);
        return () => observer.disconnect();
    }, [redraw]);

    const overlayBg = button
        ? "rgba(255, 255, 255, 0.1)"
        : "rgba(255, 255, 255, 0.05)";

    return (
        <div
            ref={wrapperRef}
            className={`${className} liquid-glass relative overflow-hidden ${button ? "cursor-pointer origin-top" : ""
                }`}
            style={
                button
                    ? {
                        transition: "all 0.3s ease-out",
                        transform: isHovering ? "scale(1.05) rotate(-1deg)" : "scale(1) rotate(0deg)",
                    }
                    : undefined
            }
            onMouseEnter={() => {
                setIsHovering(true);
            }}
            onMouseLeave={() => {
                setIsHovering(false);
            }}
        >
            {/* Overlay */}
            <div
                className="lg-overlay-bg absolute inset-0 z-[1]"
                style={{ background: overlayBg }}
            />

            {/* Animated Background */}
            {background && (
                <div className="absolute inset-0 z-0 overflow-hidden">
                    <div
                        ref={spinnerRef}
                        className="absolute top-1/2 left-1/2 w-full -translate-x-1/2 -translate-y-1/2"
                        style={{
                            animation: freeze
                                ? undefined
                                : isHovering
                                    ? "spin 20s linear infinite"
                                    : undefined,
                            willChange: "transform",
                        }}
                    >
                        <img
                            src={background}
                            alt=""
                            style={{ willChange: "filter" }}
                            draggable={false}
                        />
                    </div>
                </div>
            )}

            {/* Content */}
            <div ref={contentRef} className="lg-content relative z-[3]">
                {children}
            </div>

            {/* Filter Layer */}
            <div className="absolute inset-0 z-[2] pointer-events-none">
                <div
                    ref={glassRef}
                    className={`${className}`}
                    style={{
                        ...colorClasses[color],
                        margin: 0,
                    }}
                />
            </div>
        </div>
    );
}
