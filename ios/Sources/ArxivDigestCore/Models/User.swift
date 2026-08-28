import Foundation

/// The authenticated user (from `GET /auth/me`).
public struct User: Codable, Identifiable, Sendable {
    public let id: Int
    public let email: String
    public let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case email
        case createdAt = "created_at"
    }

    public init(id: Int, email: String, createdAt: Date) {
        self.id = id
        self.email = email
        self.createdAt = createdAt
    }
}
