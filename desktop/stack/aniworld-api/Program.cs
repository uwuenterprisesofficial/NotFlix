// AniWorld through SerienStreamAPI (https://github.com/IcySnex/SerienStreamAPI), served the way
// NotFlix's AniWorldApiProvider asks for it (backend/app/providers/aniworld.py):
//
//   GET /api/series/{title}/episodes/{season}            the season's episodes, with their
//                                                        hosters and languages
//   GET /api/series/{title}/episodes/{season}/{episode}  the episode's play links
//   GET /health
//
// {title} is the series' AniWorld slug (or its title). A series or season that doesn't exist
// answers 404. Settings: ANIWORLD_HOST (default https://aniworld.to/) and --urls.

using System.Text.Json;
using System.Text.Json.Serialization;
using SerienStreamAPI.Client;
using SerienStreamAPI.Exceptions;

var builder = WebApplication.CreateSlimBuilder(args);
builder.Services.ConfigureHttpJsonOptions(options =>
{
    options.SerializerOptions.PropertyNamingPolicy = JsonNamingPolicy.CamelCase;
    options.SerializerOptions.Converters.Add(new JsonStringEnumConverter());
});
builder.Logging.SetMinimumLevel(LogLevel.Warning);

var host = Environment.GetEnvironmentVariable("ANIWORLD_HOST") is { Length: > 0 } configured
    ? configured
    : "https://aniworld.to/";
var client = new SerienStreamClient(host, "anime");
var app = builder.Build();

app.MapGet("/health", () => Results.Ok(new { status = "ok" }));

app.MapGet("/api/series/{title}/episodes/{season:int}", async (string title, int season, CancellationToken ct) =>
    await Answer(async () => Results.Ok(await client.GetEpisodesAsync(title, season, ct))));

app.MapGet("/api/series/{title}/episodes/{season:int}/{episode:int}",
    async (string title, int season, int episode, CancellationToken ct) =>
        await Answer(async () => Results.Ok(await client.GetEpisodeVideoInfoAsync(title, episode, season, ct))));

app.Run();

static async Task<IResult> Answer(Func<Task<IResult>> work)
{
    try
    {
        return await work();
    }
    catch (Exception e) when (e is SeriesNotFoundException or SeasonNotFoundException)
    {
        return Results.NotFound(new { detail = e.Message });
    }
    catch (HttpRequestException e) when (e.StatusCode == System.Net.HttpStatusCode.NotFound)
    {
        return Results.NotFound(new { detail = e.Message });
    }
    catch (Exception e)
    {
        return Results.Problem(e.Message, statusCode: 502);
    }
}
