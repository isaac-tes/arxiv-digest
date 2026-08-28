import Foundation

/// A `URLProtocol` stub so `APIClient` can be tested without a live server.
///
/// Install by setting `config.protocolClasses = [MockURLProtocol.self]` on an
/// ephemeral `URLSessionConfiguration`, then assign `MockURLProtocol.handler`.
final class MockURLProtocol: URLProtocol, @unchecked Sendable {
    /// Produces a response + body for a given request.
    nonisolated(unsafe) static var handler: (@Sendable (URLRequest) throws -> (HTTPURLResponse, Data))?

    static func reset() { handler = nil }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = MockURLProtocol.handler else {
            client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
            return
        }
        do {
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}
