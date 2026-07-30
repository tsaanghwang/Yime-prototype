//go:build windows

package yime

import (
	"container/heap"
	"encoding/json"
	"fmt"
	"hash/fnv"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"testing"
	"time"
)

type componentLearningRank struct {
	Found     bool `json:"found"`
	Page      int  `json:"page"`
	PageIndex int  `json:"page_index"`
}

type componentLearningResult struct {
	coreTrialCoverageCase
	SampleGroup               string                `json:"sample_group"`
	Constructible             bool                  `json:"constructible"`
	ProductionTop             string                `json:"production_top"`
	ProductionTargetTop1      bool                  `json:"production_target_top1"`
	ColdTop                   string                `json:"cold_top"`
	ColdTargetTop1            bool                  `json:"cold_target_top1"`
	ColdMatchesProductionTop1 bool                  `json:"cold_matches_production_top1"`
	ColdTargetFirstPage       bool                  `json:"cold_target_first_page"`
	ColdTargetRank            componentLearningRank `json:"cold_target_rank"`
	SelectionOneMade          bool                  `json:"selection_one_made"`
	AfterOneTop               string                `json:"after_one_top"`
	AfterOneTargetTop1        bool                  `json:"after_one_target_top1"`
	SelectionTwoMade          bool                  `json:"selection_two_made"`
	AfterTwoTop               string                `json:"after_two_top"`
	AfterTwoTargetTop1        bool                  `json:"after_two_target_top1"`
	LearnedControl            bool                  `json:"learned_control"`
	BeforeRestartTop          string                `json:"before_restart_top"`
	BeforeRestartTargetTop1   bool                  `json:"before_restart_target_top1"`
	RestartEligible           bool                  `json:"restart_eligible"`
	AfterRestartTop           string                `json:"after_restart_top"`
	AfterRestartTargetTop1    bool                  `json:"after_restart_target_top1"`
	InterferenceControl       bool                  `json:"interference_control"`
	AfterLearningControlTop   string                `json:"after_learning_control_top"`
	InterferenceTop1Preserved bool                  `json:"interference_top1_preserved"`
}

type componentLearningMetrics struct {
	Cases                           int     `json:"cases"`
	Constructible                   int     `json:"constructible"`
	ProductionTargetTop1            int     `json:"production_target_top1"`
	ColdTargetTop1                  int     `json:"cold_target_top1"`
	ColdMatchesProductionTop1       int     `json:"cold_matches_production_top1"`
	ColdRetainsProductionTargetTop1 int     `json:"cold_retains_production_target_top1"`
	ColdTargetFirstPage             int     `json:"cold_target_first_page"`
	ColdTargetAnyPage               int     `json:"cold_target_any_page"`
	SelectionOneMade                int     `json:"selection_one_made"`
	AfterOneTargetTop1              int     `json:"after_one_target_top1"`
	SelectionTwoMade                int     `json:"selection_two_made"`
	AfterTwoTargetTop1              int     `json:"after_two_target_top1"`
	ColdTop1Rate                    float64 `json:"cold_top1_rate"`
	AfterOneTop1Rate                float64 `json:"after_one_top1_rate"`
	AfterTwoTop1Rate                float64 `json:"after_two_top1_rate"`
	ColdProductionTop1RetentionRate float64 `json:"cold_production_top1_retention_rate"`
	AfterOneTop1WilsonLower95       float64 `json:"after_one_top1_wilson_lower_95"`
	LearnedControls                 int     `json:"learned_controls"`
	BeforeRestartTargetTop1         int     `json:"before_restart_target_top1"`
	LearnedRetentionRate            float64 `json:"learned_retention_rate"`
	LearnedRetentionWilsonLower95   float64 `json:"learned_retention_wilson_lower_95"`
	RestartEligible                 int     `json:"restart_eligible"`
	AfterRestartTargetTop1          int     `json:"after_restart_target_top1"`
	RestartPersistenceRate          float64 `json:"restart_persistence_rate"`
	RestartWilsonLower95            float64 `json:"restart_wilson_lower_95"`
	InterferenceControls            int     `json:"interference_controls"`
	InterferenceTop1Preserved       int     `json:"interference_top1_preserved"`
	InterferencePreservationRate    float64 `json:"interference_preservation_rate"`
	InterferenceWilsonLower95       float64 `json:"interference_wilson_lower_95"`
}

type componentLearningReport struct {
	SchemaVersion    int                                 `json:"schema_version"`
	GeneratedAt      string                              `json:"generated_at"`
	Dictionary       string                              `json:"dictionary"`
	SamplesPerBucket int                                 `json:"samples_per_bucket"`
	MaxPages         int                                 `json:"max_pages"`
	SamplingPolicy   string                              `json:"sampling_policy"`
	Population       map[string]componentPopulation      `json:"production_population"`
	Summary          componentLearningMetrics            `json:"summary"`
	SampleGroups     map[string]componentLearningMetrics `json:"sample_groups"`
	EvaluationGroups map[string]componentLearningMetrics `json:"evaluation_groups"`
	LengthGroups     map[string]componentLearningMetrics `json:"length_groups"`
	Buckets          map[string]componentLearningMetrics `json:"buckets"`
	Cases            []componentLearningResult           `json:"cases"`
}

type componentPopulation struct {
	Entries                 int     `json:"entries"`
	EligibleEntries         int     `json:"eligible_entries"`
	ConstructibleEntries    int     `json:"constructible_entries"`
	Weight                  int64   `json:"weight"`
	EligibleWeight          int64   `json:"eligible_weight"`
	ConstructibleWeight     int64   `json:"constructible_weight"`
	EntryConstructibleRate  float64 `json:"entry_constructible_rate"`
	WeightConstructibleRate float64 `json:"weight_constructible_rate"`
}

type weightedCoverageHeap []coreTrialCoverageCase

func (items weightedCoverageHeap) Len() int { return len(items) }
func (items weightedCoverageHeap) Less(i, j int) bool {
	return betterCoreTrialCoverageCase(items[j], items[i])
}
func (items weightedCoverageHeap) Swap(i, j int) { items[i], items[j] = items[j], items[i] }
func (items *weightedCoverageHeap) Push(value any) {
	*items = append(*items, value.(coreTrialCoverageCase))
}
func (items *weightedCoverageHeap) Pop() any {
	old := *items
	value := old[len(old)-1]
	*items = old[:len(old)-1]
	return value
}

func componentLearningIntegerEnv(t *testing.T, name string, fallback int) int {
	t.Helper()
	raw := strings.TrimSpace(os.Getenv(name))
	if raw == "" {
		return fallback
	}
	value, err := strconv.Atoi(raw)
	if err != nil || value < 1 {
		t.Fatalf("%s must be a positive integer, got %q", name, raw)
	}
	return value
}

func loadComponentCodes(t *testing.T, path string) map[string][]string {
	t.Helper()
	codes := map[string][]string{}
	if err := visitCoreTrialDictionary(path, func(text, code string, _ int) error {
		codes[text] = append(codes[text], strings.ReplaceAll(code, " ", ""))
		return nil
	}); err != nil {
		t.Fatal(err)
	}
	return codes
}

func componentConstructible(text, code string, codes map[string][]string) bool {
	runes := []rune(text)
	if len(runes) == 0 {
		return false
	}
	reachable := make([]map[int]struct{}, len(runes)+1)
	reachable[0] = map[int]struct{}{0: {}}
	for start := 0; start < len(runes); start++ {
		if len(reachable[start]) == 0 {
			continue
		}
		for width := 1; width <= 4 && start+width <= len(runes); width++ {
			componentText := string(runes[start : start+width])
			for _, componentCode := range codes[componentText] {
				for codeStart := range reachable[start] {
					codeEnd := codeStart + len(componentCode)
					if codeEnd <= len(code) &&
						code[codeStart:codeEnd] == componentCode {
						if reachable[start+width] == nil {
							reachable[start+width] = map[int]struct{}{}
						}
						reachable[start+width][codeEnd] = struct{}{}
					}
				}
			}
		}
	}
	_, found := reachable[len(runes)][len(code)]
	return found
}

type componentLearningCase struct {
	coreTrialCoverageCase
	SampleGroup string
}

func componentLearningSampledInput(input string) bool {
	digest := fnv.New32a()
	_, _ = digest.Write([]byte(input))
	return digest.Sum32()%20 == 0
}

func loadExpandedComponentCases(
	t *testing.T,
	productionDictionary string,
	componentDictionary string,
	samplesPerBucket int,
) ([]componentLearningCase, map[string]componentPopulation) {
	t.Helper()
	componentCodes := loadComponentCodes(t, componentDictionary)
	buckets := map[string]*weightedCoverageHeap{}
	ambiguityBuckets := map[string]*weightedCoverageHeap{}
	ambiguityFirst := map[string]coreTrialCoverageCase{}
	ambiguityCompleted := map[string]struct{}{}
	population := map[string]componentPopulation{}
	if err := visitCoreTrialDictionary(
		productionDictionary,
		func(text, code string, weight int) error {
			lengthBucket, ok := coreTrialLengthBucket(text)
			if !ok {
				return nil
			}
			input := strings.ReplaceAll(code, " ", "")
			constructible := componentConstructible(text, input, componentCodes)
			eligible := true
			for _, char := range []rune(text) {
				if _, found := componentCodes[string(char)]; !found {
					eligible = false
					break
				}
			}
			for _, populationKey := range []string{"all", lengthBucket} {
				item := population[populationKey]
				item.Entries++
				item.Weight += int64(weight)
				if eligible {
					item.EligibleEntries++
					item.EligibleWeight += int64(weight)
				}
				if constructible {
					item.ConstructibleEntries++
					item.ConstructibleWeight += int64(weight)
				}
				population[populationKey] = item
			}
			key := fmt.Sprintf("length=%s,constructible=%t", lengthBucket, constructible)
			items := buckets[key]
			if items == nil {
				items = &weightedCoverageHeap{}
				heap.Init(items)
				buckets[key] = items
			}
			candidate := coreTrialCoverageCase{
				Target:       text,
				Input:        input,
				LengthBucket: lengthBucket,
				InCore:       constructible,
				Weight:       weight,
			}
			if items.Len() < samplesPerBucket {
				heap.Push(items, candidate)
			} else if betterCoreTrialCoverageCase(candidate, (*items)[0]) {
				heap.Pop(items)
				heap.Push(items, candidate)
			}
			if constructible && componentLearningSampledInput(input) {
				if _, completed := ambiguityCompleted[input]; !completed {
					if first, found := ambiguityFirst[input]; !found {
						ambiguityFirst[input] = candidate
					} else if first.Target != candidate.Target {
						alternative := candidate
						if betterCoreTrialCoverageCase(candidate, first) {
							alternative = first
						}
						ambiguityKey := alternative.LengthBucket
						ambiguityItems := ambiguityBuckets[ambiguityKey]
						if ambiguityItems == nil {
							ambiguityItems = &weightedCoverageHeap{}
							heap.Init(ambiguityItems)
							ambiguityBuckets[ambiguityKey] = ambiguityItems
						}
						if ambiguityItems.Len() < samplesPerBucket {
							heap.Push(ambiguityItems, alternative)
						} else if betterCoreTrialCoverageCase(
							alternative, (*ambiguityItems)[0],
						) {
							heap.Pop(ambiguityItems)
							heap.Push(ambiguityItems, alternative)
						}
						ambiguityCompleted[input] = struct{}{}
						delete(ambiguityFirst, input)
					}
				}
			}
			return nil
		},
	); err != nil {
		t.Fatal(err)
	}

	result := []componentLearningCase{}
	for _, length := range []string{"2", "3", "4", "5", "6", "7", "8-12"} {
		for _, constructible := range []bool{true, false} {
			key := fmt.Sprintf("length=%s,constructible=%t", length, constructible)
			items := buckets[key]
			if items == nil {
				continue
			}
			group := make([]coreTrialCoverageCase, items.Len())
			copy(group, *items)
			sort.Slice(group, func(i, j int) bool {
				return betterCoreTrialCoverageCase(group[i], group[j])
			})
			for _, item := range group {
				result = append(result, componentLearningCase{
					coreTrialCoverageCase: item,
					SampleGroup:           "constructibility_stress",
				})
			}
		}
	}
	for _, length := range []string{"2", "3", "4", "5", "6", "7", "8-12"} {
		items := ambiguityBuckets[length]
		if items == nil {
			continue
		}
		group := make([]coreTrialCoverageCase, items.Len())
		copy(group, *items)
		sort.Slice(group, func(i, j int) bool {
			return betterCoreTrialCoverageCase(group[i], group[j])
		})
		for _, item := range group {
			result = append(result, componentLearningCase{
				coreTrialCoverageCase: item,
				SampleGroup:           "same_code_alternative",
			})
		}
	}
	for key, item := range population {
		if item.Entries > 0 {
			item.EntryConstructibleRate =
				float64(item.ConstructibleEntries) / float64(item.Entries)
		}
		if item.Weight > 0 {
			item.WeightConstructibleRate =
				float64(item.ConstructibleWeight) / float64(item.Weight)
		}
		population[key] = item
	}
	return result, population
}

type componentLearningRuntime struct {
	t                 *testing.T
	dataDir           string
	userDir           string
	sessionID         RimeSessionId
	productionSession RimeSessionId
	closed            bool
}

func (runtime *componentLearningRuntime) close() {
	if runtime.closed {
		return
	}
	runtime.closed = true
	if runtime.sessionID != 0 {
		EndSession(runtime.sessionID)
		runtime.sessionID = 0
	}
	if runtime.productionSession != 0 {
		EndSession(runtime.productionSession)
		runtime.productionSession = 0
	}
	Finalize()
}

func (runtime *componentLearningRuntime) restartTrialSession() RimeSessionId {
	runtime.t.Helper()
	runtime.close()
	runtime.closed = false
	if !RimeInit(runtime.dataDir, runtime.userDir, APP, APP_VERSION, false) {
		runtime.t.Fatal("RimeInit after learning restart failed")
	}
	sessionID, ok := StartSession()
	if !ok || sessionID == 0 {
		Finalize()
		runtime.closed = true
		runtime.t.Fatal("StartSession after learning restart failed")
	}
	if !SelectSchema(sessionID, "yime_component_learning_trial") {
		EndSession(sessionID)
		Finalize()
		runtime.closed = true
		runtime.t.Fatal("could not reselect yime_component_learning_trial")
	}
	SetOption(sessionID, "ascii_mode", false)
	runtime.sessionID = sessionID
	return sessionID
}

func newComponentLearningSession(
	t *testing.T,
	dataDir string,
) *componentLearningRuntime {
	t.Helper()
	userDir := filepath.Join(t.TempDir(), "Rime")
	if err := os.MkdirAll(userDir, 0o755); err != nil {
		t.Fatal(err)
	}
	defaultCustom := "patch:\n  schema_list:\n" +
		"    - schema: yime_component_learning_trial\n" +
		"    - schema: yime_variable\n"
	if err := os.WriteFile(
		filepath.Join(userDir, "default.custom.yaml"),
		[]byte(defaultCustom),
		0o644,
	); err != nil {
		t.Fatal(err)
	}
	if !RimeInit(dataDir, userDir, APP, APP_VERSION, false) {
		t.Fatal("RimeInit failed")
	}
	sessionID, ok := StartSession()
	if !ok || sessionID == 0 {
		Finalize()
		t.Fatal("StartSession failed")
	}
	if !SelectSchema(sessionID, "yime_component_learning_trial") {
		t.Fatal("could not select yime_component_learning_trial")
	}
	SetOption(sessionID, "ascii_mode", false)
	productionSession, ok := StartSession()
	if !ok || productionSession == 0 {
		t.Fatal("could not start production comparison session")
	}
	if !SelectSchema(productionSession, "yime_variable") {
		t.Fatal("could not select yime_variable")
	}
	SetOption(productionSession, "ascii_mode", false)
	runtime := &componentLearningRuntime{
		t:                 t,
		dataDir:           dataDir,
		userDir:           userDir,
		sessionID:         sessionID,
		productionSession: productionSession,
	}
	t.Cleanup(runtime.close)
	return runtime
}

func typeAndMenu(t *testing.T, sessionID RimeSessionId, input string) coreTrialReplaySnapshot {
	t.Helper()
	ClearComposition(sessionID)
	for _, key := range []rune(input) {
		if !ProcessKey(sessionID, int(key), 0) {
			ClearComposition(sessionID)
			return coreTrialReplaySnapshot{Input: input}
		}
	}
	menu, ok := GetMenu(sessionID)
	if !ok {
		return coreTrialReplaySnapshot{Input: input}
	}
	return coreTrialReplaySnapshot{
		Input: input, PageSize: menu.PageSize, Candidates: menu.Candidates,
	}
}

func findAndSelectTarget(
	t *testing.T,
	sessionID RimeSessionId,
	input string,
	target string,
	maxPages int,
) (componentLearningRank, bool) {
	t.Helper()
	typeAndMenu(t, sessionID, input)
	for page := 0; page < maxPages; page++ {
		menu, ok := GetMenu(sessionID)
		if !ok {
			return componentLearningRank{}, false
		}
		for index, candidate := range menu.Candidates {
			if candidate.Text == target {
				selected := SelectCandidate(sessionID, index)
				if selected {
					_, _ = GetCommit(sessionID)
				}
				return componentLearningRank{
					Found: true, Page: page, PageIndex: index,
				}, selected
			}
		}
		if menu.IsLastPage || !ProcessKey(sessionID, rimeNext, 0) {
			break
		}
	}
	ClearComposition(sessionID)
	return componentLearningRank{}, false
}

func observeTargetRank(
	t *testing.T,
	sessionID RimeSessionId,
	input string,
	target string,
	maxPages int,
) (coreTrialReplaySnapshot, componentLearningRank) {
	t.Helper()
	first := typeAndMenu(t, sessionID, input)
	for page := 0; page < maxPages; page++ {
		menu, ok := GetMenu(sessionID)
		if !ok {
			break
		}
		for index, candidate := range menu.Candidates {
			if candidate.Text == target {
				ClearComposition(sessionID)
				return first, componentLearningRank{
					Found: true, Page: page, PageIndex: index,
				}
			}
		}
		if menu.IsLastPage || !ProcessKey(sessionID, rimeNext, 0) {
			break
		}
	}
	ClearComposition(sessionID)
	return first, componentLearningRank{}
}

func addComponentLearningMetrics(
	metrics *componentLearningMetrics,
	result componentLearningResult,
) {
	metrics.Cases++
	if result.Constructible {
		metrics.Constructible++
	}
	if result.ProductionTargetTop1 {
		metrics.ProductionTargetTop1++
	}
	if result.ColdTargetTop1 {
		metrics.ColdTargetTop1++
	}
	if result.ColdMatchesProductionTop1 {
		metrics.ColdMatchesProductionTop1++
	}
	if result.ProductionTargetTop1 && result.ColdTargetTop1 {
		metrics.ColdRetainsProductionTargetTop1++
	}
	if result.ColdTargetFirstPage {
		metrics.ColdTargetFirstPage++
	}
	if result.ColdTargetRank.Found {
		metrics.ColdTargetAnyPage++
	}
	if result.SelectionOneMade {
		metrics.SelectionOneMade++
	}
	if result.AfterOneTargetTop1 {
		metrics.AfterOneTargetTop1++
	}
	if result.SelectionTwoMade {
		metrics.SelectionTwoMade++
	}
	if result.AfterTwoTargetTop1 {
		metrics.AfterTwoTargetTop1++
	}
	if result.RestartEligible {
		metrics.RestartEligible++
		if result.AfterRestartTargetTop1 {
			metrics.AfterRestartTargetTop1++
		}
	}
	if result.LearnedControl {
		metrics.LearnedControls++
		if result.BeforeRestartTargetTop1 {
			metrics.BeforeRestartTargetTop1++
		}
	}
	if result.InterferenceControl {
		metrics.InterferenceControls++
		if result.InterferenceTop1Preserved {
			metrics.InterferenceTop1Preserved++
		}
	}
}

func componentWilsonLower95(successes int, cases int) float64 {
	if cases <= 0 {
		return 0
	}
	const z = 1.959963984540054
	n := float64(cases)
	p := float64(successes) / n
	z2 := z * z
	center := p + z2/(2*n)
	margin := z * math.Sqrt((p*(1-p)+z2/(4*n))/n)
	return (center - margin) / (1 + z2/n)
}

func finishComponentLearningMetrics(metrics *componentLearningMetrics) {
	if metrics.Cases == 0 {
		return
	}
	divisor := float64(metrics.Cases)
	metrics.ColdTop1Rate = float64(metrics.ColdTargetTop1) / divisor
	metrics.AfterOneTop1Rate = float64(metrics.AfterOneTargetTop1) / divisor
	metrics.AfterTwoTop1Rate = float64(metrics.AfterTwoTargetTop1) / divisor
	metrics.AfterOneTop1WilsonLower95 = componentWilsonLower95(
		metrics.AfterOneTargetTop1,
		metrics.Cases,
	)
	if metrics.ProductionTargetTop1 > 0 {
		metrics.ColdProductionTop1RetentionRate =
			float64(metrics.ColdRetainsProductionTargetTop1) /
				float64(metrics.ProductionTargetTop1)
	}
	if metrics.RestartEligible > 0 {
		metrics.RestartPersistenceRate =
			float64(metrics.AfterRestartTargetTop1) /
				float64(metrics.RestartEligible)
		metrics.RestartWilsonLower95 = componentWilsonLower95(
			metrics.AfterRestartTargetTop1,
			metrics.RestartEligible,
		)
	}
	if metrics.LearnedControls > 0 {
		metrics.LearnedRetentionRate =
			float64(metrics.BeforeRestartTargetTop1) /
				float64(metrics.LearnedControls)
		metrics.LearnedRetentionWilsonLower95 = componentWilsonLower95(
			metrics.BeforeRestartTargetTop1,
			metrics.LearnedControls,
		)
	}
	if metrics.InterferenceControls > 0 {
		metrics.InterferencePreservationRate =
			float64(metrics.InterferenceTop1Preserved) /
				float64(metrics.InterferenceControls)
		metrics.InterferenceWilsonLower95 = componentWilsonLower95(
			metrics.InterferenceTop1Preserved,
			metrics.InterferenceControls,
		)
	}
}

func TestExpandedStrictComponentLearningReplay(t *testing.T) {
	if os.Getenv("YIME_RUN_COMPONENT_LEARNING_REPLAY") != "1" {
		t.Skip("set YIME_RUN_COMPONENT_LEARNING_REPLAY=1")
	}
	componentDictionary := strings.TrimSpace(os.Getenv("YIME_COMPONENT_DICTIONARY"))
	componentRuntimeData := strings.TrimSpace(os.Getenv("YIME_COMPONENT_RUNTIME_DATA"))
	reportPath := strings.TrimSpace(os.Getenv("YIME_COMPONENT_LEARNING_REPORT"))
	if componentDictionary == "" || componentRuntimeData == "" || reportPath == "" {
		t.Fatal("YIME_COMPONENT_DICTIONARY, YIME_COMPONENT_RUNTIME_DATA and YIME_COMPONENT_LEARNING_REPORT are required")
	}
	samplesPerBucket := componentLearningIntegerEnv(t, "YIME_COMPONENT_SAMPLES_PER_BUCKET", 350)
	maxPages := componentLearningIntegerEnv(t, "YIME_COMPONENT_MAX_PAGES", 50)
	dataDir := rimeRuntimeTestDataDir(t)
	cases, population := loadExpandedComponentCases(
		t,
		filepath.Join(dataDir, "yime_variable.dict.yaml"),
		componentDictionary,
		samplesPerBucket,
	)

	runtime := newComponentLearningSession(t, componentRuntimeData)
	sessionID := runtime.sessionID
	productionSession := runtime.productionSession

	results := make([]componentLearningResult, len(cases))
	for index, testCase := range cases {
		production := typeAndMenu(t, productionSession, testCase.Input)
		cold, rank := observeTargetRank(
			t, sessionID, testCase.Input, testCase.Target, maxPages,
		)
		results[index] = componentLearningResult{
			coreTrialCoverageCase: testCase.coreTrialCoverageCase,
			SampleGroup:           testCase.SampleGroup,
			Constructible:         testCase.InCore,
			ProductionTop:         topCandidateText(production.Candidates),
			ProductionTargetTop1:  topCandidateText(production.Candidates) == testCase.Target,
			ColdTop:               topCandidateText(cold.Candidates),
			ColdTargetTop1:        topCandidateText(cold.Candidates) == testCase.Target,
			ColdMatchesProductionTop1: topCandidateText(production.Candidates) != "" &&
				topCandidateText(production.Candidates) == topCandidateText(cold.Candidates),
			ColdTargetFirstPage: candidateTextPresent(cold.Candidates, testCase.Target),
			ColdTargetRank:      rank,
		}
	}

	for index := range results {
		result := &results[index]
		if result.ColdTargetTop1 {
			result.AfterOneTop = result.ColdTop
			result.AfterOneTargetTop1 = true
			result.AfterTwoTop = result.ColdTop
			result.AfterTwoTargetTop1 = true
			continue
		}
		_, result.SelectionOneMade = findAndSelectTarget(
			t, sessionID, result.Input, result.Target, maxPages,
		)
		afterOne := typeAndMenu(t, sessionID, result.Input)
		result.AfterOneTop = topCandidateText(afterOne.Candidates)
		result.AfterOneTargetTop1 = result.AfterOneTop == result.Target
		ClearComposition(sessionID)
		if result.AfterOneTargetTop1 {
			result.AfterTwoTop = result.AfterOneTop
			result.AfterTwoTargetTop1 = true
			continue
		}
		_, result.SelectionTwoMade = findAndSelectTarget(
			t, sessionID, result.Input, result.Target, maxPages,
		)
		afterTwo := typeAndMenu(t, sessionID, result.Input)
		result.AfterTwoTop = topCandidateText(afterTwo.Candidates)
		result.AfterTwoTargetTop1 = result.AfterTwoTop == result.Target
		ClearComposition(sessionID)
	}

	// Replay corrected targets after all other selections. This separates
	// cross-case learning interference from the subsequent process restart.
	for index := range results {
		result := &results[index]
		result.LearnedControl = result.AfterTwoTargetTop1 &&
			(result.SelectionOneMade || result.SelectionTwoMade)
		if !result.LearnedControl {
			continue
		}
		learned := typeAndMenu(t, sessionID, result.Input)
		result.BeforeRestartTop = topCandidateText(learned.Candidates)
		result.BeforeRestartTargetTop1 =
			result.BeforeRestartTop == result.Target
		ClearComposition(sessionID)
	}

	// These controls were already correct in the cold pass and were never
	// explicitly selected. Replay them after all corrections to detect whether
	// unrelated learning displaced their original first choice.
	for index := range results {
		result := &results[index]
		result.InterferenceControl = result.ColdTargetTop1 &&
			!result.SelectionOneMade && !result.SelectionTwoMade
		if !result.InterferenceControl {
			continue
		}
		control := typeAndMenu(t, sessionID, result.Input)
		result.AfterLearningControlTop = topCandidateText(control.Candidates)
		result.InterferenceTop1Preserved =
			result.AfterLearningControlTop == result.ColdTop
		ClearComposition(sessionID)
	}

	// Finalize librime and reopen the exact same user directory so persistence
	// is verified from the on-disk user database, not an in-memory session.
	restartedSessionID := runtime.restartTrialSession()
	for index := range results {
		result := &results[index]
		result.RestartEligible = result.BeforeRestartTargetTop1
		if !result.RestartEligible {
			continue
		}
		restarted := typeAndMenu(t, restartedSessionID, result.Input)
		result.AfterRestartTop = topCandidateText(restarted.Candidates)
		result.AfterRestartTargetTop1 =
			result.AfterRestartTop == result.Target
		ClearComposition(restartedSessionID)
	}

	report := componentLearningReport{
		SchemaVersion:    2,
		GeneratedAt:      time.Now().Format(time.RFC3339),
		Dictionary:       componentDictionary,
		SamplesPerBucket: samplesPerBucket,
		MaxPages:         maxPages,
		SamplingPolicy: "top-weight Han-only production targets per length and " +
			"strict 1-4 component-constructibility bucket",
		Population:       population,
		LengthGroups:     map[string]componentLearningMetrics{},
		SampleGroups:     map[string]componentLearningMetrics{},
		EvaluationGroups: map[string]componentLearningMetrics{},
		Buckets:          map[string]componentLearningMetrics{},
		Cases:            results,
	}
	for _, result := range results {
		addComponentLearningMetrics(&report.Summary, result)
		length := report.LengthGroups[result.LengthBucket]
		addComponentLearningMetrics(&length, result)
		report.LengthGroups[result.LengthBucket] = length
		sampleGroup := report.SampleGroups[result.SampleGroup]
		addComponentLearningMetrics(&sampleGroup, result)
		report.SampleGroups[result.SampleGroup] = sampleGroup
		if result.Constructible && result.ProductionTargetTop1 {
			key := "constructible_and_production_top1"
			evaluation := report.EvaluationGroups[key]
			addComponentLearningMetrics(&evaluation, result)
			report.EvaluationGroups[key] = evaluation
		}
		if result.ColdTargetRank.Found {
			key := "target_reachable_in_menu"
			evaluation := report.EvaluationGroups[key]
			addComponentLearningMetrics(&evaluation, result)
			report.EvaluationGroups[key] = evaluation
		}
		bucketKey := fmt.Sprintf(
			"length=%s,constructible=%t", result.LengthBucket, result.Constructible,
		)
		bucket := report.Buckets[bucketKey]
		addComponentLearningMetrics(&bucket, result)
		report.Buckets[bucketKey] = bucket
	}
	finishComponentLearningMetrics(&report.Summary)
	for key, metrics := range report.LengthGroups {
		finishComponentLearningMetrics(&metrics)
		report.LengthGroups[key] = metrics
	}
	for key, metrics := range report.SampleGroups {
		finishComponentLearningMetrics(&metrics)
		report.SampleGroups[key] = metrics
	}
	for key, metrics := range report.EvaluationGroups {
		finishComponentLearningMetrics(&metrics)
		report.EvaluationGroups[key] = metrics
	}
	for key, metrics := range report.Buckets {
		finishComponentLearningMetrics(&metrics)
		report.Buckets[key] = metrics
	}
	data, err := json.MarshalIndent(report, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	data = append(data, '\n')
	if err := os.MkdirAll(filepath.Dir(reportPath), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(reportPath, data, 0o644); err != nil {
		t.Fatal(err)
	}
	t.Logf("COMPONENT_LEARNING_SUMMARY %s", mustJSON(report.Summary))
}

func mustJSON(value any) string {
	data, err := json.Marshal(value)
	if err != nil {
		return fmt.Sprintf(`{"error":%q}`, err.Error())
	}
	return string(data)
}
