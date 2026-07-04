import SwiftUI

/// A simple wrapping layout: lays children left-to-right and wraps to the next line
/// when they overflow the available width. Used for flag/tag pills so they reflow
/// gracefully at large Dynamic Type sizes. Requires iOS 16 (`Layout`).
struct FlowRow: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout Void) -> CGSize {
        let maxWidth = proposal.width ?? .infinity
        let rows = arrange(subviews: subviews, maxWidth: maxWidth)
        return rows.bounds
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout Void) {
        let rows = arrange(subviews: subviews, maxWidth: bounds.width)
        for placement in rows.placements {
            let point = CGPoint(x: bounds.minX + placement.x, y: bounds.minY + placement.y)
            placement.subview.place(at: point, proposal: ProposedViewSize(placement.size))
        }
    }

    // MARK: - Arrangement

    private struct Placement {
        let subview: LayoutSubview
        let size: CGSize
        var x: CGFloat
        var y: CGFloat
    }

    private struct Arranged {
        var placements: [Placement]
        var bounds: CGSize
    }

    private func arrange(subviews: Subviews, maxWidth: CGFloat) -> Arranged {
        var placements: [Placement] = []
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        var maxRowWidth: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)

            if x > 0, x + size.width > maxWidth {
                // Wrap to next row.
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }

            placements.append(Placement(subview: subview, size: size, x: x, y: y))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
            maxRowWidth = max(maxRowWidth, x - spacing)
        }

        let totalHeight = y + rowHeight
        let width = maxWidth.isFinite ? min(maxRowWidth, maxWidth) : maxRowWidth
        return Arranged(placements: placements, bounds: CGSize(width: width, height: totalHeight))
    }
}
