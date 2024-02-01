"use client";

import { useRef, useState } from "react";
import { SearchBar } from "./SearchBar";
import { SearchResultsDisplay } from "./SearchResultsDisplay";
import { SourceSelector } from "./filtering/Filters";
import { SearchLanguageSelector } from "./SearchLanguageSelector";
import { Connector, DocumentSet, Tag } from "@/lib/types";
import {
  DanswerDocument,
  Quote,
  SearchResponse,
  FlowType,
  SearchType,
  SearchDefaultOverrides,
  SearchRequestOverrides,
  ValidQuestionResponse,
} from "@/lib/search/interfaces";
import { searchRequestStreamed } from "@/lib/search/streamingQa";
import { SearchHelper } from "./SearchHelper";
import { CancellationToken, cancellable } from "@/lib/search/cancellable";
import { useFilters, useObjectState } from "@/lib/hooks";
import { questionValidationStreamed } from "@/lib/search/streamingQuestionValidation";
import { Persona } from "@/app/admin/personas/interfaces";
import { PersonaSelector } from "./PersonaSelector";

const SEARCH_DEFAULT_OVERRIDES_START: SearchDefaultOverrides = {
  forceDisplayQA: false,
  offset: 0,
};

const VALID_QUESTION_RESPONSE_DEFAULT: ValidQuestionResponse = {
  reasoning: null,
  answerable: null,
  error: null,
};

interface SearchSectionProps {
  connectors: Connector<any>[];
  documentSets: DocumentSet[];
  personas: Persona[];
  tags: Tag[];
  defaultSearchType: SearchType;
}

export const SearchSection = ({
  connectors,
  documentSets,
  personas,
  tags,
  defaultSearchType,
}: SearchSectionProps) => {
  // Search Bar
  const [query, setQuery] = useState<string>("");
  const [language, setLanguage] = useState<string>("english");

  // Search
  const [searchResponse, setSearchResponse] = useState<SearchResponse | null>(
    null
  );
  const [isFetching, setIsFetching] = useState(false);

  const [validQuestionResponse, setValidQuestionResponse] =
    useObjectState<ValidQuestionResponse>(VALID_QUESTION_RESPONSE_DEFAULT);

  // Filters
  const filterManager = useFilters();

  // Search Type
  const [selectedSearchType, setSelectedSearchType] =
    useState<SearchType>(defaultSearchType);

  const [selectedPersona, setSelectedPersona] = useState<number>(
    personas[0]?.id || 0
  );

  // Overrides for default behavior that only last a single query
  const [defaultOverrides, setDefaultOverrides] =
    useState<SearchDefaultOverrides>(SEARCH_DEFAULT_OVERRIDES_START);

  // Helpers
  const initialSearchResponse: SearchResponse = {
    answer: null,
    quotes: null,
    documents: null,
    suggestedSearchType: null,
    suggestedFlowType: null,
    selectedDocIndices: null,
    error: null,
    queryEventId: null,
  };
  const updateCurrentAnswer = (answer: string) =>
    setSearchResponse((prevState) => ({
      ...(prevState || initialSearchResponse),
      answer,
    }));
  const updateQuotes = (quotes: Quote[]) =>
    setSearchResponse((prevState) => ({
      ...(prevState || initialSearchResponse),
      quotes,
    }));
  const updateDocs = (documents: DanswerDocument[]) =>
    setSearchResponse((prevState) => ({
      ...(prevState || initialSearchResponse),
      documents,
    }));
  const updateSuggestedSearchType = (suggestedSearchType: SearchType) =>
    setSearchResponse((prevState) => ({
      ...(prevState || initialSearchResponse),
      suggestedSearchType,
    }));
  const updateSuggestedFlowType = (suggestedFlowType: FlowType) =>
    setSearchResponse((prevState) => ({
      ...(prevState || initialSearchResponse),
      suggestedFlowType,
    }));
  const updateSelectedDocIndices = (docIndices: number[]) =>
    setSearchResponse((prevState) => ({
      ...(prevState || initialSearchResponse),
      selectedDocIndices: docIndices,
    }));
  const updateError = (error: FlowType) =>
    setSearchResponse((prevState) => ({
      ...(prevState || initialSearchResponse),
      error,
    }));
  const updateQueryEventId = (queryEventId: number) =>
    setSearchResponse((prevState) => ({
      ...(prevState || initialSearchResponse),
      queryEventId,
    }));

  let lastSearchCancellationToken = useRef<CancellationToken | null>(null);
  const onSearch = async ({
    searchType,
    offset,
    query,
  }: SearchRequestOverrides & { query: string }) => {
    // cancel the prior search if it hasn't finished
    if (lastSearchCancellationToken.current) {
      lastSearchCancellationToken.current.cancel();
    }
    lastSearchCancellationToken.current = new CancellationToken();

    setIsFetching(true);
    setSearchResponse(initialSearchResponse);
    setValidQuestionResponse(VALID_QUESTION_RESPONSE_DEFAULT);

    const searchFnArgs = {
      query,
      sources: filterManager.selectedSources,
      documentSets: filterManager.selectedDocumentSets,
      timeRange: filterManager.timeRange,
      tags: filterManager.selectedTags,
      persona: personas.find(
        (persona) => persona.id === selectedPersona
      ) as Persona,
      updateCurrentAnswer: cancellable({
        cancellationToken: lastSearchCancellationToken.current,
        fn: updateCurrentAnswer,
      }),
      updateQuotes: cancellable({
        cancellationToken: lastSearchCancellationToken.current,
        fn: updateQuotes,
      }),
      updateDocs: cancellable({
        cancellationToken: lastSearchCancellationToken.current,
        fn: updateDocs,
      }),
      updateSuggestedSearchType: cancellable({
        cancellationToken: lastSearchCancellationToken.current,
        fn: updateSuggestedSearchType,
      }),
      updateSuggestedFlowType: cancellable({
        cancellationToken: lastSearchCancellationToken.current,
        fn: updateSuggestedFlowType,
      }),
      updateSelectedDocIndices: cancellable({
        cancellationToken: lastSearchCancellationToken.current,
        fn: updateSelectedDocIndices,
      }),
      updateError: cancellable({
        cancellationToken: lastSearchCancellationToken.current,
        fn: updateError,
      }),
      updateQueryEventId: cancellable({
        cancellationToken: lastSearchCancellationToken.current,
        fn: updateQueryEventId,
      }),
      selectedSearchType: searchType ?? selectedSearchType,
      offset: offset ?? defaultOverrides.offset,
    };

    const questionValidationArgs = {
      query,
      update: setValidQuestionResponse,
    };

    // await Promise.all([
    //   searchRequestStreamed(searchFnArgs),
    //   questionValidationStreamed(questionValidationArgs),
    // ]);
    const [tempSearchResponse, tempValidationResponse] = await Promise.all([
      searchRequestStreamed(searchFnArgs),
      questionValidationStreamed(questionValidationArgs),
    ]);



    setIsFetching(false);

    return tempSearchResponse.answer;
  };

  const translateToEnglish = async (text: string): Promise<string> => {
    const response = await fetch('https://qo4le5gdg10o34m1.us-east-1.aws.endpoints.huggingface.cloud', {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer NSBAjgJJBYZFSyJQnKhWtqbnDiMjhvPZvEiJjwvqVoeojQjEpiGBimUYzwodfspAVLnISwxpBFmFHDZCRUkGcKOoymZGByldmNjRpGWYbCblafXvbEqOYdgZoOpJdAFk',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        'inputs': text,
        'parameters': {
          'temperature': 0.5, 'top_k': 5,
          'top_p': 1.0, 'max_new_tokens': 512, 'repetition_penalty': 1.0
        }
      }),
    });

    const data = await response.json();
    console.log(data)
    console.log('inside translate luganda to english function')
    console.log(data[0].generated_text)
    return data[0].generated_text;  // Assuming the translated text is returned in this key
  };

  const translateToLuganda = async (text: string | null): Promise<string> => {
    if (text != null) {
      const response = await fetch('https://t90ai8edum2silwl.us-east-1.aws.endpoints.huggingface.cloud', {
        method: 'POST',
        headers: {
          "Authorization": "Bearer NSBAjgJJBYZFSyJQnKhWtqbnDiMjhvPZvEiJjwvqVoeojQjEpiGBimUYzwodfspAVLnISwxpBFmFHDZCRUkGcKOoymZGByldmNjRpGWYbCblafXvbEqOYdgZoOpJdAFk",
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          'inputs': text, 'parameters': {
            'temperature': 0.5, 'top_k': 5,
            'top_p': 1.0, 'max_new_tokens': 512, 'repetition_penalty': 1.0
          }
        }),
      });

      const data = await response.json();
      console.log('inside translate english to luganda function')
      console.log(data[0].generated_text) //generated_text translation_text
      return data[0].generated_text; //generated_text // Assuming the translated text is returned in this 
    } else {
      console.log('error: input text is null')
      return "input text is null"
    }
  };

  const onSearchInLuganda = async ({
    searchType,
    offset,
  }: SearchRequestOverrides = {}) => {
    try {
      console.log('translating to english')
      // Step 1: Translate query from Luganda to English

      //   await translateToEnglish(query).then(result => {
      //     console.log("Translated result:", result);
      //     console.log ('after the translating function has been called')
      //     console.log(result);
      //   console.log ('end of  the translating function part 1')
      // }).catch(error => {
      //     console.error("Error translating:", error);
      // });

      const translatedQuery = await translateToEnglish(query)
      console.log('after the translating function has been called')
      console.log(translatedQuery);
      console.log('end of  the translating function part2')
      // Step 2: Perform search with the translated query
      // Assuming onSearch can take an optional query parameter to override the state
      //console.log('updating the query variable')
      //setQuery(translatedQuery)
      console.log('updated query value')
      console.log(query)
      const englishSearchResponse = await onSearch({ searchType, offset, query: translatedQuery });
      console.log('updated search response value from english')
      console.log(searchResponse)
      console.log(englishSearchResponse)
      // Step 3: Translate search results back to Luganda
      // Here you might need to pick the relevant fields from the search response to translate
      var englishResponse: string | null = ""
      if (englishSearchResponse) {

        //englishResponse = searchResponse.answer
        let lugandaSearchResponse = await translateToLuganda(englishSearchResponse);
        //lugandaSearchResponse = lugandaSearchResponse.replace(/_/g, ' ');
        console.log('translated answer back to luganda')
        console.log(lugandaSearchResponse)


        // Step 4: Update state with Luganda search results
        updateCurrentAnswer(lugandaSearchResponse)
        // setSearchResponse({
        //   ...searchResponse,
        //   answer: lugandaSearchResponse
        // });

      } else {
        var lugandaSearchResponseFailed = 'Failed to respond in Luganda'
        //updateCurrentAnswer(lugandaSearchResponseFailed)

        //  setSearchResponse({
        //    ...searchResponse,
        //   answer: lugandaSearchResponseFailed
        //  })
      }



    } catch (error) {
      setSearchResponse(initialSearchResponse);
      console.error('An error occurred during the Luganda search:', error);
    }
  };

  return (
    <div className="relative max-w-[2000px] xl:max-w-[1430px] mx-auto">
      <div className="absolute left-0 hidden 2xl:block w-64">
        {/* {(connectors.length > 0 || documentSets.length > 0) && (
          <SourceSelector
            {...filterManager}
            availableDocumentSets={documentSets}
            existingSources={connectors.map((connector) => connector.source)}
            availableTags={tags}
          />
        )} */}

        <div className="mt-10 pr-5">
          <SearchHelper
            isFetching={isFetching}
            searchResponse={searchResponse}
            selectedSearchType={selectedSearchType}
            setSelectedSearchType={setSelectedSearchType}
            defaultOverrides={defaultOverrides}
            //restartSearch={onSearch}
            forceQADisplay={() =>
              setDefaultOverrides((prevState) => ({
                ...(prevState || SEARCH_DEFAULT_OVERRIDES_START),
                forceDisplayQA: true,
              }))
            }
            setOffset={(offset) => {
              setDefaultOverrides((prevState) => ({
                ...(prevState || SEARCH_DEFAULT_OVERRIDES_START),
                offset,
              }));
            }}
          />
        </div>
      </div>
      <div className="w-[800px] mx-auto">
        {personas.length > 0 ? (
          <div className="flex mb-2 w-fit">
            <PersonaSelector
              personas={personas}
              selectedPersonaId={selectedPersona}
              onPersonaChange={(persona) => setSelectedPersona(persona.id)}
            />
          </div>
        ) : (
          <div className="pt-3" />
        )}

        <SearchLanguageSelector
          language={language}
          setLanguage={(language: string) => {
            setLanguage(language)
          }}
        />

        <SearchBar
          query={query}
          setQuery={setQuery}
          language={language}
          onSearch={async () => {
            setDefaultOverrides(SEARCH_DEFAULT_OVERRIDES_START);
            await onSearch({ offset: 0, query });
          }}
        />

        <div className="mt-2">
          <SearchResultsDisplay
            searchResponse={searchResponse}
            validQuestionResponse={validQuestionResponse}
            isFetching={isFetching}
            defaultOverrides={defaultOverrides}
            personaName={
              selectedPersona
                ? personas.find((p) => p.id === selectedPersona)?.name
                : null
            }
          />
        </div>
      </div>
    </div>
  );
};
